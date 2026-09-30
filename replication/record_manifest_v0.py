#!/usr/bin/env python3
"""Write immutable, secret-free provenance for a replication-v0 phase."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("baseline", "launch-12h", "resume-36h"))
    parser.add_argument("--submission-log", type=Path)
    args = parser.parse_args()

    repo = Path(os.environ["AAR_REPO"]).resolve()
    root = Path(os.environ["AAR_RUNTIME_ROOT"])
    output = root / "metadata" / f"manifest-{args.phase}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"refusing to overwrite retained manifest: {output}")

    files: list[Path] = [repo / "uv.lock"]
    model = Path(os.environ["TARGET_MODEL_PATH"])
    files.extend(
        model / name
        for name in (
            "config.json", "generation_config.json", "tokenizer_config.json",
            "model.safetensors.index.json",
        )
        if (model / name).is_file()
    )
    for optional in (
        Path(os.environ["AAR_BASELINE_OVERRIDES"]),
        Path(os.environ["HOLDOUT_DIR"]) / "sycophancy" / "sycophancy.yaml",
        Path(os.environ["AAR_SERVE_V2_DEPLOYMENT_DIR"]) / "spec.yaml",
    ):
        if optional.is_file():
            files.append(optional)

    job_ids: list[str] = []
    if args.submission_log and args.submission_log.is_file():
        text = args.submission_log.read_text()
        job_ids = sorted(set(re.findall(r"(?:job |-> job )(\d+)", text)))
        files.append(args.submission_log)

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase,
        "git_branch": subprocess.check_output(
            ["git", "-C", str(repo), "branch", "--show-current"], text=True
        ).strip(),
        "git_commit": subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip(),
        "model_identity": "google/gemma-4-31B-it",
        "model_path": str(model),
        "serve_deployment": os.environ["AAR_SERVE_V2_DEPLOYMENT_DIR"],
        "served_model": os.environ["AAR_SERVE_V2_MODEL"],
        "suite_benchmarks": os.environ["AAR_SUITE_BENCHMARKS"].split(),
        "thinking_enabled": os.environ.get("AAR_TARGET_ENABLE_THINKING") == "1",
        "agent_model": os.environ.get("AAR_AGENT_MODEL"),
        "agent_effort": os.environ.get("AAR_EFFORT"),
        "slurm": {
            "account": os.environ["AAR_SLURM_ACCOUNT"],
            "partition": os.environ["AAR_SLURM_PARTITION"],
            "qos": os.environ["AAR_TRAIN_QOS"],
            "training_gpus": int(os.environ["AAR_TRAIN_GPUS"]),
            "evaluator_gpus": int(os.environ["AAR_EVAL_GPUS"]),
            "max_concurrent_training_jobs": int(os.environ["AAR_MAX_CONCURRENT_TRAIN_JOBS"]),
        },
        "team_id": os.environ["AAR_TEAM_ID"],
        "job_ids": job_ids,
        "sha256": {str(path): digest(path) for path in files},
    }
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
