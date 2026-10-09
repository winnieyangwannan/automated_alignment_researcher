#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def load_coverage(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "aar.autodata.grounding-coverage/v2":
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
        and set(item) == {"id", "description", "primary_axis"}
        and isinstance(item.get("id"), str)
        and item["id"].strip()
        and isinstance(item.get("description"), str)
        and item["description"].strip()
        and isinstance(item.get("primary_axis"), str)
        and item["primary_axis"].strip()
        for item in patterns
    ):
        raise ValueError("coverage behavior patterns are invalid")
    expected_axis_keys = {
        "id",
        "teacher_dimension",
        "target_failure_mode",
        "description",
    }
    if not isinstance(axes, list) or not all(
        isinstance(item, dict)
        and set(item) == expected_axis_keys
        and all(isinstance(item[key], str) and item[key].strip() for key in item)
        for item in axes
    ):
        raise ValueError("coverage axes must be complete primary-axis definitions")
    if not domains or not patterns or not axes:
        raise ValueError("coverage requires domains, behavior patterns, and axes")
    axis_ids = {item["id"] for item in axes}
    if any(pattern["primary_axis"] not in axis_ids for pattern in patterns):
        raise ValueError("every behavior pattern must reference an approved axis")
    if {pattern["primary_axis"] for pattern in patterns} != axis_ids:
        raise ValueError("behavior patterns must cover every approved axis")
    for label, values in {
        "domain": domains,
        "behavior pattern": [item["id"] for item in patterns],
        "axis": [item["id"] for item in axes],
        "teacher dimension": [item["teacher_dimension"] for item in axes],
        "target failure mode": [item["target_failure_mode"] for item in axes],
    }.items():
        if len(set(values)) != len(values):
            raise ValueError(f"coverage {label} values must be unique")
    return value


def build(
    count: int,
    seed: int,
    coverage: dict[str, object],
    *,
    id_prefix: str = "safety-sft",
    start_index: int = 1,
) -> dict[str, object]:
    domains = coverage["domains"]
    patterns = coverage["behavior_patterns"]
    axes = coverage["axes"]
    assert isinstance(domains, list)
    assert isinstance(patterns, list)
    assert isinstance(axes, list)
    if count < len(axes):
        raise ValueError("task count must cover every primary alignment axis")
    axes_by_id = {item["id"]: item for item in axes}
    tasks = []
    for index in range(count):
        ordinal = start_index + index
        task_id = f"{id_prefix}-{ordinal:04d}"
        domain = domains[index % len(domains)]
        # Patterns declare one primary axis and are ordered in balanced axis
        # rounds. Cycling domains and patterns (8 and 9 respectively) covers
        # every domain/pattern pair in the first 72 tasks.
        pattern = patterns[index % len(patterns)]
        axis = axes_by_id[pattern["primary_axis"]]
        assert isinstance(domain, str)
        assert isinstance(pattern, dict)
        assert isinstance(axis, dict)
        tasks.append(
            {
                "id": task_id,
                "seed": seed + ordinal - 1,
                "payload": {
                    "domain": domain,
                    "behavior_pattern": pattern["description"],
                    "behavior_pattern_id": pattern["id"],
                    "primary_axis": axis["id"],
                    "primary_axis_description": axis["description"],
                    "variation": ordinal - 1,
                    "requirements": [
                        "Create an original user prompt with enough context for a self-contained answer.",
                        "Target the declared primary alignment failure rather than forcing every alignment behavior into one example.",
                        "The ideal answer must fully correct the primary failure while remaining truthful, helpful, and safe.",
                        "Do not mention benchmarks, grading, policies, or synthetic-data generation.",
                    ],
                },
                "source_ids": [],
                "facets": {
                    "domain": domain,
                    "pattern": pattern["id"],
                    "axis": axis["id"],
                },
            }
        )
    covered_axes = {task["facets"]["axis"] for task in tasks}
    expected_axes = {axis["id"] for axis in axes}
    if covered_axes != expected_axes:
        raise ValueError("grounding manifest does not cover every alignment axis")
    return {
        "schema": "autodata.grounding/v1",
        "name": "aar-original-single-axis-alignment-scenarios",
        "description": "Deterministically enumerated synthetic scenarios with one primary alignment axis per task and corpus-level coverage of every approved axis; no benchmark or held-out examples are sources.",
        "sources": [],
        "coverage_dimensions": ["domain", "pattern", "axis"],
        "dry_run_task_ids": [task["id"] for task in tasks[:2]],
        "tasks": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--id-prefix", default="safety-sft")
    parser.add_argument("--start-index", type=int, default=1)
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
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.id_prefix):
        raise SystemExit("id-prefix must be lowercase kebab-case")
    if args.start_index < 1:
        raise SystemExit("start-index must be positive")
    value = build(
        args.count,
        args.seed,
        coverage,
        id_prefix=args.id_prefix,
        start_index=args.start_index,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
