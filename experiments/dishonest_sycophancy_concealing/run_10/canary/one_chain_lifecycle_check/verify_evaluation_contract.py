#!/usr/bin/env python3
"""Fail closed unless a lifecycle suite contains exactly the configured items."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import yaml


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_suite(
    suite_path: Path, expected_benchmarks: list[str], expected_items: int
) -> dict[str, object]:
    payload = yaml.safe_load(suite_path.read_text())
    if not isinstance(payload, dict):
        raise RuntimeError("suite YAML must contain a mapping")
    entries = payload.get("benchmarks")
    if not isinstance(entries, list):
        raise RuntimeError("suite YAML has no benchmark list")
    names = [entry.get("name") for entry in entries if isinstance(entry, dict)]
    if names != expected_benchmarks or len(entries) != len(expected_benchmarks):
        raise RuntimeError(
            f"expected benchmarks {expected_benchmarks}, found {names}"
        )

    data: dict[str, dict[str, object]] = {}
    for entry, name in zip(entries, expected_benchmarks, strict=True):
        if entry.get("subset_size") != expected_items:
            raise RuntimeError(
                f"{name} subset_size is {entry.get('subset_size')!r}, "
                f"expected {expected_items}"
            )
        data_path = suite_path.parent / f"{name}.jsonl"
        records = [line for line in data_path.read_text().splitlines() if line.strip()]
        if len(records) != expected_items:
            raise RuntimeError(
                f"{name} contains {len(records)} records, expected {expected_items}"
            )
        for index, line in enumerate(records, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"{name} record {index} is invalid JSON") from error
            if not isinstance(value, dict):
                raise RuntimeError(f"{name} record {index} is not an object")
        data[name] = {
            "path": str(data_path),
            "records": len(records),
            "sha256": _sha256(data_path),
        }

    return {
        "schema_version": 1,
        "status": "passed",
        "suite": payload.get("suite"),
        "suite_path": str(suite_path),
        "suite_sha256": _sha256(suite_path),
        "expected_benchmarks": expected_benchmarks,
        "expected_items_per_benchmark": expected_items,
        "published_data": data,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--benchmarks", required=True)
    parser.add_argument("--items", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    benchmarks = [name for name in args.benchmarks.replace(",", " ").split() if name]
    if not benchmarks:
        parser.error("--benchmarks must name at least one benchmark")
    if args.items < 1:
        parser.error("--items must be positive")

    proof = verify_suite(args.suite.resolve(strict=True), benchmarks, args.items)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
