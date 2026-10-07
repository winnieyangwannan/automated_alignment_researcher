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
from typing import Any, Mapping, Optional

from aar import config


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
    if is_adapter:
        _validate_finite_adapter_weights(path)
    return path


# --- model handoff (research -> eval) --------------------------------------
def _submission_metadata(metadata: Mapping[str, Any] | None, run_id: str) -> dict[str, Any] | None:
    if metadata is None:
        return None
    value = dict(metadata)
    if value.get("schema") != "aar.model-submission/v1":
        raise ValueError("model submission metadata has an unsupported schema")
    if value.get("run_id") != run_id:
        raise ValueError("model submission metadata run_id mismatch")
    # Round-trip now so non-JSON values fail before the model is advertised.
    return json.loads(json.dumps(value, sort_keys=True))


def put_model(
    model_path: str,
    run_id: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Research side: publish the trained model for run_id. Returns its ref."""
    source = validate_model_submission(model_path)
    submission_metadata = _submission_metadata(metadata, run_id)
    if _fs():
        dest = Path(config.SUBMISSIONS_DIR) / run_id / "model"
        dest.parent.mkdir(parents=True, exist_ok=True)
        marker = dest.parent / ".submitted"
        marker.unlink(missing_ok=True)
        (dest.parent / "submission_metadata.json").unlink(missing_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        _copytree_retry(source, dest)
        # Check the actual staged tree, rather than assuming every shared-FS
        # copy retained all files, before advertising it to a worker.
        validate_model_submission(str(dest))
        if submission_metadata is not None:
            metadata_path = dest.parent / "submission_metadata.json"
            temporary = metadata_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(submission_metadata, indent=2, sort_keys=True) + "\n")
            os.replace(temporary, metadata_path)
        # Atomicity marker: the eval worker only picks up run_ids once this exists
        # (so it never scores a half-copied model).
        marker.touch()
        return str(dest)
    from aar.infrastructure import s3_utils
    prefix = f"{config.SUBMISSION_PREFIX}{run_id}/model"
    s3_utils.upload_directory_to_s3(source, prefix, config.S3_BUCKET)
    if submission_metadata is not None:
        with tempfile.TemporaryDirectory(prefix="aar-submission-metadata-") as temporary:
            metadata_path = Path(temporary) / "submission_metadata.json"
            metadata_path.write_text(
                json.dumps(submission_metadata, indent=2, sort_keys=True) + "\n"
            )
            s3_utils.upload_file_to_s3(
                metadata_path,
                f"{config.SUBMISSION_PREFIX}{run_id}/submission_metadata.json",
                config.S3_BUCKET,
                content_type="application/json",
            )
    return f"s3://{config.S3_BUCKET}/{prefix}"


def get_model_submission_metadata(run_id: str) -> dict[str, Any] | None:
    """Eval side: read the metadata atomically published with a model."""
    if _fs():
        path = Path(config.SUBMISSIONS_DIR) / run_id / "submission_metadata.json"
        if not path.is_file() or path.is_symlink():
            return None
        value = json.loads(path.read_text())
    else:
        from aar.infrastructure import s3_utils

        client = s3_utils.get_s3_client()
        try:
            obj = client.get_object(
                Bucket=config.S3_BUCKET,
                Key=f"{config.SUBMISSION_PREFIX}{run_id}/submission_metadata.json",
            )
        except Exception:
            return None
        value = json.loads(obj["Body"].read())
    if not isinstance(value, dict):
        raise ValueError("model submission metadata is not an object")
    return _submission_metadata(value, run_id)


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
