#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_coverage(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "aar.autodata.grounding-coverage/v1":
        raise ValueError("invalid grounding coverage schema")
    domains = value.get("domains")
    patterns = value.get("behavior_patterns")
    axes = value.get("axes")
    if not isinstance(domains, list) or not all(
        isinstance(item, str) and item.strip() for item in domains
    ):
        raise ValueError("coverage domains must be non-empty strings")
    if not isinstance(patterns, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"].strip()
        and isinstance(item.get("description"), str)
        and item["description"].strip()
        for item in patterns
    ):
        raise ValueError("coverage behavior patterns are invalid")
    if not isinstance(axes, list) or not all(
        isinstance(item, str) and item.strip() for item in axes
    ):
        raise ValueError("coverage axes must be non-empty strings")
    if not domains or not patterns or not axes:
        raise ValueError("coverage requires domains, behavior patterns, and axes")
    return value


def build(count: int, seed: int, coverage: dict[str, object]) -> dict[str, object]:
    domains = coverage["domains"]
    patterns = coverage["behavior_patterns"]
    axes = coverage["axes"]
    assert isinstance(domains, list)
    assert isinstance(patterns, list)
    assert isinstance(axes, list)
    tasks = []
    for index in range(count):
        task_id = f"safety-sft-{index + 1:04d}"
        domain = domains[index % len(domains)]
        pattern = patterns[(index // len(domains)) % len(patterns)]
        assert isinstance(domain, str)
        assert isinstance(pattern, dict)
        tasks.append(
            {
                "id": task_id,
                "seed": seed + index,
                "payload": {
                    "domain": domain,
                    "behavior_pattern": pattern["description"],
                    "behavior_pattern_id": pattern["id"],
                    "variation": index,
                    "requirements": [
                        "Create an original user prompt with enough context for a self-contained answer.",
                        "The ideal answer must be truthful, resist social pressure, and calibrate uncertainty.",
                        "Do not mention benchmarks, grading, policies, or synthetic-data generation.",
                    ],
                },
                "source_ids": [],
                "facets": {
                    "domain": domain,
                    "pattern": pattern["id"],
                    "axis": axes,
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
    parser.add_argument(
        "--coverage",
        type=Path,
        default=Path(__file__).with_name("coverage.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    coverage = load_coverage(args.coverage)
    minimum = coverage.get("minimum_task_count")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise SystemExit("coverage minimum_task_count must be a positive integer")
    if args.count < minimum:
        raise SystemExit(f"grounding requires at least {minimum} tasks")
    value = build(args.count, args.seed, coverage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
