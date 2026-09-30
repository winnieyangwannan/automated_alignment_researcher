#!/usr/bin/env python3
"""Convert a full baseline evaluation result into a run-local baseline override."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED = {"sycophancy_eval", "sycon_fp", "mmlu", "gsm8k", "ifeval"}
MODEL = "google/gemma-4-31B-it"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    result = json.loads(args.result.read_text())
    per_benchmark = result.get("per_benchmark") or {}
    missing = EXPECTED - set(per_benchmark)
    extra = set(per_benchmark) - EXPECTED
    if missing or extra:
        raise SystemExit(f"baseline benchmark mismatch: missing={sorted(missing)} extra={sorted(extra)}")

    scores: dict[str, dict] = {}
    for name in sorted(EXPECTED):
        raw = per_benchmark[name]
        scores[name] = {
            "mean": float(raw["mean"]),
            "ci_low": float(raw["ci_low"]),
            "ci_high": float(raw["ci_high"]),
            "n": int(raw["n"]),
        }
        if scores[name]["n"] <= 0:
            raise SystemExit(f"baseline {name} has no scored examples")
    syc = scores["sycophancy_eval"]
    if not 0.05 < syc["mean"] < 0.95:
        raise SystemExit(
            "sycophancy_eval baseline has insufficient two-sided headroom: "
            f"mean={syc['mean']}"
        )
    payload = {
        "axis": "sycophancy",
        "model": MODEL,
        "source_result": str(args.result.resolve()),
        "scores": {MODEL: scores},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite retained baseline: {args.output}")
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
