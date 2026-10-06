"""Atomic, held-out-safe terminal failure handoff for evaluator workers."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


def publish_failure(
    scores_dir: str | Path,
    run_id: str,
    reason: str,
    *,
    eval_job_id: str | None = None,
) -> Path:
    """Publish an idempotent terminal failure without exposing partial scores."""
    if not run_id or Path(run_id).name != run_id:
        raise ValueError("run_id must be one nonempty path component")

    directory = Path(scores_dir)
    directory.mkdir(parents=True, exist_ok=True)
    success_path = directory / f"{run_id}.json"
    failure_path = directory / f"{run_id}.failed.json"
    if success_path.exists():
        raise FileExistsError(f"refusing to replace successful score: {success_path}")
    if failure_path.exists():
        return failure_path

    payload = {
        "status": "failed",
        "run_id": run_id,
        "reason": reason,
        "eval_job_id": eval_job_id,
    }
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--eval-job-id", default=os.getenv("SLURM_JOB_ID"))
    args = parser.parse_args()
    print(
        publish_failure(
            args.scores_dir,
            args.run_id,
            args.reason,
            eval_job_id=args.eval_job_id,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
