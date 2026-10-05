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
    parser.add_argument(
        "--phase",
        required=True,
        choices=(
            "baseline",
            "canary",
            "two-iteration-pilot",
            "launch-12h",
            "resume-36h",
        ),
    )
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
        Path(os.environ["HOLDOUT_DIR"])
        / os.environ.get("SUITE_NAME", "sycophancy")
        / f"{os.environ.get('SUITE_NAME', 'sycophancy')}.yaml",
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
        "thinking_plus_answer_token_budget": int(
            os.environ["EVAL_RUN_GEN_CEILING"]
        ),
        "judge": {
            "backend": os.environ.get("JUDGE_BACKEND"),
            "model": os.environ.get("JUDGE_MODEL"),
        },
        "evaluation_health": {
            "batch_size": int(os.environ["EVAL_RUN_BATCH"]),
            "freeform_generation_ceiling": int(
                os.environ["EVAL_RUN_GEN_CEILING"]
            ),
            "generation_ceiling_benchmarks": os.environ[
                "EVAL_RUN_GEN_CEILING_BENCHMARKS"
            ].replace(",", " ").split(),
            "fail_on_allocator_warning": os.environ.get(
                "EVAL_FAIL_ON_ALLOCATOR_WARNING"
            ) == "1",
            "max_truncation_rate": float(os.environ["EVAL_MAX_TRUNCATION_RATE"]),
            "truncation_min_completions": int(
                os.environ["EVAL_TRUNCATION_MIN_COMPLETIONS"]
            ),
        },
        "agent_model": os.environ.get("AAR_AGENT_MODEL"),
        "agent_effort": os.environ.get("AAR_EFFORT"),
        "monitor": {
            "backend": os.environ.get("AAR_MONITOR_BACKEND"),
            "model": os.environ.get("MONITOR_MODEL"),
        },
        "librarian_model": os.environ.get("LITREVIEW_MODEL"),
        "dimensions": os.environ.get("AAR_DIMENSIONS", "").split(","),
        "petri": {"mode": "post_hoc_only", "included_in_optimization": False},
        "functional_smoke": os.environ.get("AAR_FUNCTIONAL_SMOKE") == "1",
        "held_out_isolation": (
            "functional_smoke_same_user"
            if os.environ.get("AAR_FUNCTIONAL_SMOKE") == "1"
            else "separate_evaluator_principal_required"
        ),
        "authorized_spend_caps_usd": {
            "claude": os.environ.get("AAR_CLAUDE_SPEND_CAP_USD"),
            "gpt_judges": os.environ.get("AAR_GPT_JUDGE_SPEND_CAP_USD"),
        },
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
