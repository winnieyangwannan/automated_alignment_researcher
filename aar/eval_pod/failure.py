"""Atomic, held-out-safe terminal failure handoff for evaluator workers."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Callable

from aar.failure_feedback import sanitize_failure_summary


_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_STAGE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def classify_failure_error_code(
    *, stage: str, error_code: str, reason: object
) -> str:
    """Refine generic training failures into actionable, content-free codes."""

    if stage != "training" or error_code not in {
        "training_process_failed",
        "training_python_exception",
    }:
        return error_code
    normalized = " ".join(str(reason).lower().split())
    if any(
        token in normalized
        for token in (
            "zero valid example",
            "no valid example",
            "empty dataset",
            "dataset is empty",
            "num_samples should be a positive integer",
        )
    ):
        return "training_dataset_empty"
    if (
        ("chosen" in normalized or "rejected" in normalized)
        and any(token in normalized for token in ("string", "str", "text"))
    ):
        return "training_preference_schema_invalid"
    if "loss" in normalized and any(
        token in normalized
        for token in (
            "without a loss",
            "did not return a loss",
            "loss is none",
            "no loss",
        )
    ):
        return "training_loss_missing"
    if (
        "unexpected keyword argument" in normalized
        or "got an unexpected keyword" in normalized
    ):
        return "training_api_mismatch"
    if (
        "list" in normalized
        and "has no attribute" in normalized
        and "map" in normalized
    ):
        return "training_dataset_interface_invalid"
    if "methodconfig" in normalized and "has no attribute" in normalized:
        return "training_method_config_invalid"
    if (
        "nonetype" in normalized
        and any(operator in normalized for operator in (">", "<", ">=", "<="))
        and "int" in normalized
    ):
        return "training_optional_integer_invalid"
    if "target modules" in normalized and any(
        token in normalized
        for token in ("not found", "did not match", "no target", "cannot find")
    ):
        return "training_peft_target_mismatch"
    if any(
        token in normalized
        for token in (
            "cuda out of memory",
            "cuda error: out of memory",
            "torch.outofmemoryerror",
        )
    ):
        return "training_cuda_out_of_memory"
    if any(
        token in normalized
        for token in (
            "mat1 and mat2 shapes cannot be multiplied",
            "size mismatch",
            "shape mismatch",
            "must have the same shape",
        )
    ):
        return "training_tensor_shape_mismatch"
    if ("pad_token" in normalized or "padding token" in normalized) and any(
        token in normalized for token in ("not set", "none", "missing", "undefined")
    ):
        return "training_tokenizer_configuration_invalid"
    return error_code


def sanitize_failure_text(value: object, *, limit: int = 1000) -> str:
    """Return a compact diagnostic that is safe for the research-side handoff."""

    return sanitize_failure_summary(value, limit=limit)


def publish_failure(
    scores_dir: str | Path,
    run_id: str,
    reason: str,
    *,
    eval_job_id: str | None = None,
    stage: str = "evaluation",
    error_code: str = "evaluator_rejected",
    retryable: bool = False,
    disposition: str | None = None,
    exception_type: str | None = None,
    exit_code: int | None = None,
    log_path: str | Path | None = None,
    replace_invalid: bool = False,
) -> Path:
    """Publish an idempotent, structured failure without exposing partial scores.

    ``reason`` crosses to research-readable storage and therefore must already
    be non-content-bearing. This function additionally bounds and redacts common
    credential forms, but cannot infer whether arbitrary text contains held-out
    prompts or rows.
    """
    if not run_id or Path(run_id).name != run_id:
        raise ValueError("run_id must be one nonempty path component")
    if not _STAGE_RE.fullmatch(stage):
        raise ValueError("stage must be a lowercase identifier")
    error_code = classify_failure_error_code(
        stage=stage, error_code=error_code, reason=reason
    )
    if not _ERROR_CODE_RE.fullmatch(error_code):
        raise ValueError("error_code must be a lowercase identifier")
    if disposition is None:
        disposition = (
            "retry_operation"
            if retryable
            else "advance_session" if stage in {"training", "evaluation"} else "halt"
        )
    if disposition not in {"retry_operation", "advance_session", "halt"}:
        raise ValueError("invalid failure disposition")

    directory = Path(scores_dir)
    directory.mkdir(parents=True, exist_ok=True)
    success_path = directory / f"{run_id}.json"
    failure_path = directory / f"{run_id}.failed.json"
    if success_path.exists():
        raise FileExistsError(f"refusing to replace successful score: {success_path}")
    if failure_path.exists() or failure_path.is_symlink():
        if not replace_invalid:
            return failure_path
        existing: object = None
        if not failure_path.is_symlink() and failure_path.is_file():
            try:
                existing = json.loads(failure_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        if (
            isinstance(existing, dict)
            and existing.get("schema_version") == 2
            and existing.get("status") == "failed"
            and existing.get("run_id") == run_id
            and isinstance(existing.get("stage"), str)
            and _STAGE_RE.fullmatch(existing["stage"]) is not None
            and isinstance(existing.get("error_code"), str)
            and _ERROR_CODE_RE.fullmatch(existing["error_code"]) is not None
            and isinstance(existing.get("retryable"), bool)
        ):
            return failure_path

    safe_reason = sanitize_failure_text(reason)
    payload: dict[str, object] = {
        "schema_version": 2,
        "status": "failed",
        "run_id": run_id,
        "stage": stage,
        "error_code": error_code,
        "retryable": retryable,
        "disposition": disposition,
        # Keep both keys while older research clients still distinguish training
        # ("error") from evaluation ("reason") failure markers.
        "error": safe_reason,
        "reason": safe_reason,
    }
    if eval_job_id:
        payload["eval_job_id"] = sanitize_failure_text(eval_job_id, limit=128)
    if exception_type:
        payload["exception_type"] = sanitize_failure_text(exception_type, limit=128)
    if exit_code is not None:
        payload["exit_code"] = int(exit_code)
    if log_path:
        payload["log_path"] = sanitize_failure_text(log_path, limit=1000)
    fd, temporary_name = tempfile.mkstemp(
        dir=directory,
        prefix=f".{run_id}.failed.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o640)
        os.replace(temporary_path, failure_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return failure_path


def install_uncaught_exception_failure_hook(
    scores_dir: str | Path,
    run_id: str,
    *,
    stage: str,
    error_code: str,
    log_path: str | Path | None = None,
) -> Callable[[type[BaseException], BaseException, TracebackType | None], None]:
    """Publish a sanitized marker before Python prints an uncaught traceback."""

    prior_hook = sys.excepthook

    def _hook(
        exception_class: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        try:
            publish_failure(
                scores_dir,
                run_id,
                str(exception) or exception_class.__name__,
                stage=stage,
                error_code=error_code,
                retryable=False,
                exception_type=exception_class.__name__,
                exit_code=1,
                log_path=log_path,
            )
        except Exception:
            # Failure reporting must never mask the original exception.
            pass
        prior_hook(exception_class, exception, traceback)

    sys.excepthook = _hook
    return _hook


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--eval-job-id", default=os.getenv("SLURM_JOB_ID"))
    parser.add_argument("--stage", default="evaluation")
    parser.add_argument("--error-code", default="evaluator_rejected")
    parser.add_argument("--retryable", action="store_true")
    parser.add_argument(
        "--disposition",
        choices=("retry_operation", "advance_session", "halt"),
    )
    parser.add_argument("--exception-type")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--log-path")
    args = parser.parse_args()
    print(
        publish_failure(
            args.scores_dir,
            args.run_id,
            args.reason,
            eval_job_id=args.eval_job_id,
            stage=args.stage,
            error_code=args.error_code,
            retryable=args.retryable,
            disposition=args.disposition,
            exception_type=args.exception_type,
            exit_code=args.exit_code,
            log_path=args.log_path,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
