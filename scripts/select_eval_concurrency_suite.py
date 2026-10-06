#!/usr/bin/env python3
"""Build a public-only, size-capped suite for evaluator throughput tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--benchmark", action="append", required=True)
    parser.add_argument("--subset-size-cap", type=int, required=True)
    args = parser.parse_args()

    if args.subset_size_cap < 1:
        parser.error("--subset-size-cap must be positive")

    suite = yaml.safe_load(args.source.read_text())
    requested = list(dict.fromkeys(args.benchmark))
    selected = []
    found: set[str] = set()
    for benchmark in suite.get("benchmarks", []):
        if benchmark.get("role") == "held_out":
            continue
        identities = {str(benchmark.get("id", "")), str(benchmark.get("name", ""))}
        matches = [name for name in requested if name in identities]
        if not matches:
            continue
        item = dict(benchmark)
        current = item.get("subset_size")
        item["subset_size"] = (
            min(int(current), args.subset_size_cap)
            if current
            else args.subset_size_cap
        )
        selected.append(item)
        found.update(matches)

    missing = [name for name in requested if name not in found]
    if missing:
        raise RuntimeError(f"benchmarks missing from source suite: {missing}")
    if len(selected) < 2:
        raise RuntimeError("throughput suite requires at least two benchmarks")

    suite["benchmarks"] = selected
    represented_dimensions = {
        item.get("dimension")
        for item in selected
        if item.get("role", "safety") == "safety" and item.get("dimension")
    }
    suite["dimensions"] = [
        dimension
        for dimension in suite.get("dimensions", [])
        if (
            dimension if isinstance(dimension, str) else dimension.get("name")
        ) in represented_dimensions
    ]
    suite["suite"] = f"{suite.get('suite', 'suite')}_throughput"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(suite, sort_keys=False))
    print(
        f"wrote {args.output} with {len(selected)} public benchmarks "
        f"capped at {args.subset_size_cap} items"
    )


if __name__ == "__main__":
    main()
