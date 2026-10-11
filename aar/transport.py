"""Transport layer: how the trained model + scores move between the research
side and the eval side, and where the secret suite is read from.

Two backends, selected by config.HARNESS_TRANSPORT:

- "fs" (default) — shared filesystem (VAST). Model is copied under
  SUBMISSIONS_DIR/<run_id>/model/; the eval reads it + the secret suite from
  HOLDOUT_DIR in place (no copy); scores are written back next to the model.
  Isolation = file permissions (HOLDOUT_DIR owned by a separate eval user,
  mode 700), which also prevents accidental deletion by the AAR.

- "s3" — S3-compatible object store, for infra with no shared filesystem.
  Isolation = scoped credentials.

Everything else in the harness calls these functions and stays
transport-agnostic.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from aar import config


_ADAPTER_TRANSPORT_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "adapter_model.bin",
)


def _fs() -> bool:
    return config.HARNESS_TRANSPORT == "fs"


def _copytree_retry(src, dst, attempts: int = 4):
    """copytree that retries transient shared-FS errors (NFS 'Stale file handle'
    [Errno 116] / Errno 521 seen on the VAST mount during the train->submissions
    model handoff). A transient FS error must not lose a finished training run; we
    back off and retry, cleaning a partial dest each time, before giving up."""
    last = None
    for i in range(attempts):
        try:
            shutil.copytree(src, dst)
            return
        except (OSError, shutil.Error) as e:
            last = e
            shutil.rmtree(dst, ignore_errors=True)
            if i < attempts - 1:
                time.sleep(2 ** i)   # 1,2,4s
    raise last


def _copy_adapter_retry(src: Path, dst: Path, attempts: int = 4) -> None:
    """Copy only final PEFT artifacts, never Trainer checkpoints or tokenizers."""

    last: OSError | shutil.Error | None = None
    for index in range(attempts):
        try:
            dst.mkdir(parents=True)
            for name in _ADAPTER_TRANSPORT_FILES:
                source = src / name
                if source.is_file():
                    shutil.copy2(source, dst / name)
            return
        except (OSError, shutil.Error) as error:
            last = error
            shutil.rmtree(dst, ignore_errors=True)
            if index < attempts - 1:
                time.sleep(2**index)
    if last is not None:
        raise last
    raise RuntimeError("adapter copy failed without an exception")


def _validate_finite_adapter_weights(path: Path) -> None:
    """Reject a PEFT safetensors adapter containing NaN or infinite values.

    The check runs before the atomic ``.submitted`` marker is created, so an
    optimizer-diverged adapter never enters the evaluator queue.  Reading one
    tensor at a time keeps peak host memory bounded by the largest LoRA tensor.
    """
    weights = path / "adapter_model.safetensors"
    if not weights.is_file():
        return

    try:
        import torch
        from safetensors import safe_open
    except ImportError as exc:  # fail closed when an adapter cannot be checked
        raise RuntimeError(
            "validating PEFT adapter weights requires torch and safetensors"
        ) from exc

    bad_names: list[str] = []
    tensor_count = 0
    with safe_open(str(weights), framework="pt", device="cpu") as handle:
        for name in handle.keys():
            tensor_count += 1
            if not torch.isfinite(handle.get_tensor(name)).all().item():
                if len(bad_names) < 5:
                    bad_names.append(name)

    if tensor_count == 0:
        raise ValueError("PEFT adapter contains no tensors")
    if bad_names:
        raise ValueError(
            "PEFT adapter contains non-finite weights (NaN/Inf); "
            f"examples: {', '.join(bad_names)}"
        )


def validate_model_submission(model_path: str) -> Path:
    """Fail fast unless *model_path* is a self-contained HF submission.

    The evaluator loads the staged directory with ``from_pretrained``.  In
    particular, Qwen submissions need both their tokenizer assets and either a
    full set of model weights or a PEFT adapter.  Catching an incomplete
    ``save_pretrained`` output before creating ``.submitted`` avoids spending a
    queued GPU evaluation on a checkpoint that cannot possibly load.

    This is deliberately a structural check: loading multi-GB weights here
    would duplicate the model in memory at the end of training.  The evaluator
    remains the authoritative runtime load check.
    """
    path = Path(model_path)
    if not path.is_dir():
        raise ValueError(f"model submission must be a directory: {model_path!r}")

    is_full_model = (path / "config.json").is_file()
    is_adapter = (path / "adapter_config.json").is_file()
    if os.getenv("AAR_REQUIRE_ADAPTER", "0").lower() in ("1", "true", "yes") and not is_adapter:
        raise ValueError(
            "this run requires a PEFT adapter submission; full merged checkpoints "
            "are disabled by AAR_REQUIRE_ADAPTER"
        )
    if not (is_full_model or is_adapter):
        raise ValueError(
            "model submission is missing config.json or adapter_config.json; "
            "save the model with save_pretrained(output_dir)"
        )

    weight_files = (
        list(path.glob("model*.safetensors"))
        + list(path.glob("pytorch_model*.bin"))
        + list(path.glob("adapter_model*.safetensors"))
        + list(path.glob("adapter_model*.bin"))
    )
    if not any(p.is_file() for p in weight_files):
        raise ValueError(
            "model submission has no model/adapter weights; save the model "
            "with save_pretrained(output_dir)"
        )

    if is_adapter:
        _validate_finite_adapter_weights(path)
    else:
        if not (path / "tokenizer_config.json").is_file():
            raise ValueError(
                "model submission is missing tokenizer_config.json; save the "
                "tokenizer next to the model with tokenizer.save_pretrained(output_dir)"
            )
        tokenizer_assets = (
            "tokenizer.json",
            "tokenizer.model",
            "spiece.model",
            "sentencepiece.bpe.model",
            "vocab.json",
            "vocab.txt",
        )
        if not any((path / name).is_file() for name in tokenizer_assets):
            raise ValueError(
                "model submission has tokenizer_config.json but no tokenizer "
                "vocabulary/model asset"
            )
    return path


def prune_terminal_adapter_submission(
    submission_dir: str | Path,
    terminal_marker: str | Path,
    *,
    retention: str = "all",
) -> dict[str, int | str]:
    """Retain one final adapter after a terminal score and remove transport waste."""

    if retention != "all":
        raise ValueError("only adapter retention policy 'all' is currently supported")
    submission = Path(submission_dir)
    marker = Path(terminal_marker)
    if submission.is_symlink() or marker.is_symlink():
        raise ValueError("submission and terminal marker must not be symlinks")
    submission = submission.resolve(strict=True)
    marker = marker.resolve(strict=True)
    run_id = submission.name
    if marker.name not in {f"{run_id}.json", f"{run_id}.failed.json"}:
        raise ValueError("terminal marker does not match the submission run id")
    payload = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("terminal marker must contain a JSON object")
    if marker.name.endswith(".failed.json"):
        if (
            payload.get("schema_version") != 2
            or payload.get("status") != "failed"
            or payload.get("run_id") != run_id
        ):
            raise ValueError("failure marker does not contain the submission run id")
    elif (
        not isinstance(payload.get("suite"), str)
        or not isinstance(payload.get("per_benchmark"), dict)
    ):
        raise ValueError("successful terminal marker is not an evaluation score")

    model = submission / "model"
    if model.is_symlink() or not model.is_dir():
        raise ValueError("submission model directory is missing or unsafe")
    adapter_config = model / "adapter_config.json"
    weights = [
        model / name
        for name in ("adapter_model.safetensors", "adapter_model.bin")
        if (model / name).is_file() and (model / name).stat().st_size > 0
    ]
    if not adapter_config.is_file() or not weights:
        raise ValueError("terminal submission does not contain a complete final adapter")

    allowed = {adapter_config.name, *(path.name for path in weights)}
    removed_files = 0
    removed_directories = 0
    removed_bytes = 0
    for path in model.iterdir():
        if path.name in allowed:
            continue
        if path.is_symlink():
            removed_bytes += path.lstat().st_size
            path.unlink()
            removed_files += 1
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and not child.is_symlink():
                    removed_bytes += child.stat().st_size
            shutil.rmtree(path)
            removed_directories += 1
        else:
            removed_bytes += path.stat().st_size
            path.unlink()
            removed_files += 1
    return {
        "run_id": run_id,
        "retention": retention,
        "removed_bytes": removed_bytes,
        "removed_files": removed_files,
        "removed_directories": removed_directories,
    }


# --- model handoff (research -> eval) --------------------------------------
def put_model(model_path: str, run_id: str) -> str:
    """Research side: publish the trained model for run_id. Returns its ref."""
    source = validate_model_submission(model_path)
    if _fs():
        dest = Path(config.SUBMISSIONS_DIR) / run_id / "model"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        if (source / "adapter_config.json").is_file():
            _copy_adapter_retry(source, dest)
        else:
            _copytree_retry(source, dest)
        # Check the actual staged tree, rather than assuming every shared-FS
        # copy retained all files, before advertising it to a worker.
        validate_model_submission(str(dest))
        # Atomicity marker: the eval worker only picks up run_ids once this exists
        # (so it never scores a half-copied model).
        (dest.parent / ".submitted").touch()
        return str(dest)
    from aar.infrastructure import s3_utils
    prefix = f"{config.SUBMISSION_PREFIX}{run_id}/model"
    if (source / "adapter_config.json").is_file():
        with tempfile.TemporaryDirectory(prefix="aar-adapter-submit-") as temporary:
            staged = Path(temporary) / "model"
            _copy_adapter_retry(source, staged)
            s3_utils.upload_directory_to_s3(staged, prefix, config.S3_BUCKET)
    else:
        s3_utils.upload_directory_to_s3(source, prefix, config.S3_BUCKET)
    return f"s3://{config.S3_BUCKET}/{prefix}"


def get_model(run_id: str, dest_dir: Optional[str] = None) -> str:
    """Eval side: obtain a local path to the submitted model."""
    if _fs():
        return str(Path(config.SUBMISSIONS_DIR) / run_id / "model")
    from aar.infrastructure import s3_utils
    dest = Path(dest_dir or f"./eval_work/{run_id}/model")
    dest.mkdir(parents=True, exist_ok=True)
    s3_utils.download_s3_directory(dest, config.S3_BUCKET, f"{config.SUBMISSION_PREFIX}{run_id}/model/", force_download=True, description="model")
    return str(dest)


# --- secret suite (eval side reads only) -----------------------------------
def resolve_suite_dir(suite: str, dest_dir: Optional[str] = None) -> str:
    """Eval side: local path to the secret suite dir (test inputs + answers +
    <suite>.yaml). FS: read HOLDOUT_DIR in place. S3: download from secret prefix."""
    if _fs():
        return str(Path(config.HOLDOUT_DIR) / suite)
    from aar.infrastructure import s3_utils
    dest = Path(dest_dir or f"./eval_work/secret/{suite}")
    dest.mkdir(parents=True, exist_ok=True)
    s3_utils.download_s3_directory(dest, config.S3_BUCKET, f"{config.SECRET_DATA_PREFIX}{suite}/", force_download=True, description="secret suite")
    return str(dest)


# --- scores (eval -> research/orchestrator) --------------------------------
def put_scores(run_id: str, scores: dict[str, Any]) -> str:
    """Eval side: publish scores for run_id (the completion signal). Written to
    the SCORES_DIR channel (eval-writable, research-readable), so the eval user
    never writes into the research user's submission dirs."""
    payload = json.dumps(scores, indent=2)
    if _fs():
        path = Path(config.SCORES_DIR) / f"{run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
        return str(path)
    from aar.infrastructure import s3_utils
    tmp = Path(f"./eval_work/{run_id}/scores.json")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(payload)
    s3_utils.upload_file_to_s3(tmp, f"{config.SUBMISSION_PREFIX}{run_id}/scores.json", config.S3_BUCKET, content_type="application/json")
    return f"s3://{config.S3_BUCKET}/{config.SUBMISSION_PREFIX}{run_id}/scores.json"


def read_scores(run_id: str) -> Optional[dict[str, Any]]:
    """Research/orchestrator side: return scores if present yet, else None."""
    if _fs():
        path = Path(config.SCORES_DIR) / f"{run_id}.json"
        if path.exists():
            return json.loads(path.read_text())
        return None
    from aar.infrastructure import s3_utils
    s3 = s3_utils.get_s3_client()
    try:
        obj = s3.get_object(Bucket=config.S3_BUCKET, Key=f"{config.SUBMISSION_PREFIX}{run_id}/scores.json")
        return json.loads(obj["Body"].read())
    except Exception:
        return None
