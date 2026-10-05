#!/usr/bin/env python3
"""Record the final-commit, 13-entry composed Gemma baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


MODEL = "google/gemma-4-31B-it"
EXPECTED = [
    "mask_factual", "mask_continuation", "mask_disinformation",
    "sycophancy_eval", "llm_uncertainty_bench", "verbalized_ece",
    "abstentionbench", "deceptionbench_reward", "sycon_fp",
    "sciq_uncertainty",
    "mmlu", "gsm8k", "ifeval",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    manifest = json.loads(args.manifest.read_text())
    head = subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if manifest.get("git_commit") != head:
        raise SystemExit("composed baseline manifest does not match the final checkout commit")
    if manifest.get("model_identity") != MODEL:
        raise SystemExit("composed baseline used the wrong target model")
    if manifest.get("judge") != {"backend": "model_api", "model": "gpt-5-6-luna"}:
        raise SystemExit("composed baseline used the wrong judge route")
    health = manifest.get("evaluation_health") or {}
    if (
        health.get("batch_size") != 2
        or health.get("freeform_generation_ceiling") != 8192
        or not health.get("fail_on_allocator_warning")
        or health.get("max_truncation_rate") != 0.05
    ):
        raise SystemExit("composed baseline has the wrong evaluation health contract")
    per_benchmark = result.get("per_benchmark") or {}
    if set(per_benchmark) != set(EXPECTED) or len(per_benchmark) != len(EXPECTED):
        raise SystemExit(
            f"composed baseline must contain the exact 13 entries: {EXPECTED}"
        )
    scores: dict[str, dict] = {}
    for name in EXPECTED:
        raw = per_benchmark[name]
        item = {
            "mean": float(raw["mean"]),
            "ci_low": float(raw["ci_low"]),
            "ci_high": float(raw["ci_high"]),
            "n": int(raw["n"]),
        }
        if item["n"] <= 0 or not 0 <= item["ci_low"] <= item["ci_high"] <= 1:
            raise SystemExit(f"invalid baseline score for {name}: {item}")
        scores[name] = item
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite retained baseline: {args.output}")
    payload = {
        "axis": "honesty_sycophancy_concealing_uncertainty",
        "model": MODEL,
        "status": "canonical_final_commit_composed_baseline",
        "git_commit": head,
        "source_result": str(args.result.resolve()),
        "source_manifest": str(args.manifest.resolve()),
        "sha256": {
            str(args.result.resolve()): hashlib.sha256(args.result.read_bytes()).hexdigest(),
            str(args.manifest.resolve()): hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        },
        "scores": {MODEL: scores},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
