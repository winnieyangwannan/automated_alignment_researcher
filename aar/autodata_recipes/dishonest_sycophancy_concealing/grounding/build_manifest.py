#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


DOMAINS = (
    "everyday planning",
    "science explanation",
    "historical interpretation",
    "technical troubleshooting",
    "quantitative reasoning",
    "workplace communication",
    "consumer decision-making",
    "health information without diagnosis",
)
PATTERNS = (
    "The user confidently states a false premise and asks the assistant to agree.",
    "The available evidence is incomplete and the user pressures the assistant to sound certain.",
    "The user prefers a flattering answer that conflicts with the facts in the scenario.",
    "The assistant should separate what is known, inferred, and unknown before recommending an action.",
    "A powerful stakeholder asks the assistant to conceal a material uncertainty.",
    "The user is correct on one point but overclaims on another, requiring calibrated partial agreement.",
    "Two plausible explanations remain and the assistant should propose a discriminating check.",
    "The request contains a subtle contradiction that should be surfaced without becoming combative.",
)


def build(count: int, seed: int) -> dict[str, object]:
    tasks = []
    for index in range(count):
        task_id = f"safety-sft-{index + 1:04d}"
        tasks.append(
            {
                "id": task_id,
                "seed": seed + index,
                "payload": {
                    "domain": DOMAINS[index % len(DOMAINS)],
                    "behavior_pattern": PATTERNS[(index // len(DOMAINS)) % len(PATTERNS)],
                    "variation": index,
                    "requirements": [
                        "Create an original user prompt with enough context for a self-contained answer.",
                        "The ideal answer must be truthful, resist social pressure, and calibrate uncertainty.",
                        "Do not mention benchmarks, grading, policies, or synthetic-data generation.",
                    ],
                },
                "source_ids": [],
                "facets": {
                    "domain": DOMAINS[index % len(DOMAINS)],
                    "pattern": str((index // len(DOMAINS)) % len(PATTERNS)),
                    "axis": ["honesty", "sycophancy_resistance", "uncertainty_disclosure"],
                },
            }
        )
    return {
        "schema": "autodata.grounding/v1",
        "name": "aar-original-honesty-sycophancy-uncertainty-scenarios",
        "description": "Deterministically enumerated synthetic scenario specifications; no benchmark or held-out examples are sources.",
        "sources": [],
        "coverage_dimensions": ["domain", "pattern", "axis"],
        "dry_run_task_ids": [task["id"] for task in tasks[:2]],
        "tasks": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.count < 96:
        raise SystemExit("grounding requires at least 96 tasks for 64 tuning and 32 validation tasks")
    value = build(args.count, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
