"""Fail-closed consumption of a native AutoData dataset export."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA = "aar.autodata.native-consumption/v1"


def _usage_roles(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    usage = item.get("_autodata_usage")
    if not isinstance(usage, list):
        raise ValueError("AutoData item has no provider-usage evidence")
    result: dict[str, dict[str, Any]] = {}
    for entry in usage:
        if not isinstance(entry, dict) or entry.get("role") not in {"generator", "judge"}:
            raise ValueError("AutoData item has malformed provider usage")
        role = str(entry["role"])
        if role in result:
            raise ValueError(f"AutoData item repeats {role} usage")
        for key in ("request_id", "model", "input_tokens", "output_tokens"):
            if entry.get(key) in {None, ""}:
                raise ValueError(f"AutoData {role} usage is missing {key}")
        result[role] = entry
    if set(result) != {"generator", "judge"}:
        raise ValueError("AutoData item must contain generator and judge usage")
    return result


def load_autodata_dataset(
    dataset_path: str | Path,
    *,
    receipt_path: str | Path,
    required_rows: int,
    expected_execution_id: str,
    generator_model: str = "Kimi-K2.6",
    judge_model: str = "gpt-5-6-luna",
    judge_threshold: float = 0.75,
    judge_rubric_version: str = "run9-anchored-v1",
) -> list[dict[str, Any]]:
    """Validate, load, and record consumption of one production export."""
    if isinstance(required_rows, bool) or required_rows < 1:
        raise ValueError("required_rows must be a positive integer")
    source = Path(dataset_path).resolve(strict=True)
    if source.is_symlink() or not source.is_file():
        raise ValueError("AutoData dataset must be a regular file")
    payload = source.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict) or value.get("schema") != "autodata.dataset/v1":
        raise ValueError("unsupported native AutoData dataset schema")
    if value.get("mode") != "production":
        raise ValueError("training requires a separate native production execution")
    if value.get("execution_id") != expected_execution_id:
        raise ValueError("AutoData dataset execution binding does not match")
    items = value.get("items")
    if not isinstance(items, list) or len(items) < required_rows:
        raise ValueError("AutoData dataset did not reach the required accepted-row target")
    seen: set[str] = set()
    total_input = total_output = 0
    total_cost = 0.0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"AutoData item {index} is not an object")
        for key in ("id", "prompt", "response"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"AutoData item {index} requires non-empty {key}")
        if item["id"] in seen:
            raise ValueError("AutoData dataset contains duplicate item IDs")
        seen.add(item["id"])
        metadata = item.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("judge_accepted") is not True:
            raise ValueError("AutoData dataset contains a judge-rejected item")
        score = metadata.get("judge_score")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or float(score) < judge_threshold
        ):
            raise ValueError("AutoData dataset contains a row below the fixed judge threshold")
        if metadata.get("judge_rubric_version") != judge_rubric_version:
            raise ValueError("AutoData judge rubric identity does not match")
        dimensions = metadata.get("judge_dimensions")
        expected_dimensions = {
            "self_containment",
            "factual_honesty",
            "sycophancy_resistance",
            "uncertainty_disclosure",
            "helpfulness",
            "safety",
        }
        if not isinstance(dimensions, dict) or set(dimensions) != expected_dimensions:
            raise ValueError("AutoData row lacks fixed per-dimension judge evidence")
        if any(
            not isinstance(value, dict)
            or value.get("pass") is not True
            or value.get("score") not in {0, 1, 2}
            for value in dimensions.values()
        ):
            raise ValueError("AutoData row failed a fixed judge dimension")
        roles = _usage_roles(item)
        if roles["generator"]["model"] != generator_model:
            raise ValueError("AutoData generator identity does not match")
        if roles["judge"]["model"] != judge_model:
            raise ValueError("AutoData judge identity does not match")
        for usage in roles.values():
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            if (
                isinstance(input_tokens, bool)
                or not isinstance(input_tokens, int)
                or input_tokens < 0
                or isinstance(output_tokens, bool)
                or not isinstance(output_tokens, int)
                or output_tokens < 0
            ):
                raise ValueError("AutoData provider token usage is invalid")
            total_input += input_tokens
            total_output += output_tokens
            try:
                total_cost += float(usage["estimated_cost_usd"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("AutoData provider cost usage is invalid") from error
    digest = hashlib.sha256(payload).hexdigest()
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "execution_id": expected_execution_id,
        "dataset_sha256": "sha256:" + digest,
        "row_count": len(items),
        "required_rows": required_rows,
        "generator_model": generator_model,
        "judge_model": judge_model,
        "model_calls": len(items) * 2,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "estimated_cost_usd": format(total_cost, ".12g"),
        "loaded_at_unix": time.time(),
        "consumer_pid": os.getpid(),
    }
    destination = Path(receipt_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        if destination.is_symlink():
            raise ValueError("AutoData consumption receipt must not be a symlink")
        existing = json.loads(destination.read_text())
        stable = {key: value for key, value in receipt.items() if key not in {"loaded_at_unix", "consumer_pid"}}
        if any(existing.get(key) != value for key, value in stable.items()):
            raise ValueError("existing AutoData consumption receipt does not match")
        return items
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(receipt, output, sort_keys=True, indent=2)
        output.write("\n")
    return items


def load_autodata_campaign_datasets(
    dataset_paths: list[str | Path],
    *,
    receipt_path: str | Path,
    required_rows: int,
    expected_execution_ids: list[str],
    generator_model: str = "Kimi-K2.6",
    judge_model: str = "gpt-5-6-luna",
    judge_threshold: float = 0.75,
    judge_rubric_version: str = "run9-anchored-v1",
) -> list[dict[str, Any]]:
    """Verify bounded production batches and retain exactly the target rows."""
    if len(dataset_paths) != len(expected_execution_ids) or not dataset_paths:
        raise ValueError("production datasets and execution ids must be paired")
    combined: list[dict[str, Any]] = []
    digests: list[str] = []
    execution_ids: list[str] = []
    temporary_receipts: list[Path] = []
    destination = Path(receipt_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        for index, (path, execution_id) in enumerate(
            zip(dataset_paths, expected_execution_ids, strict=True)
        ):
            source = Path(path).resolve(strict=True)
            payload = source.read_bytes()
            batch_receipt = destination.parent / f".{destination.name}.batch-{index}"
            temporary_receipts.append(batch_receipt)
            batch = load_autodata_dataset(
                source,
                receipt_path=batch_receipt,
                required_rows=1,
                expected_execution_id=execution_id,
                generator_model=generator_model,
                judge_model=judge_model,
                judge_threshold=judge_threshold,
                judge_rubric_version=judge_rubric_version,
            )
            combined.extend(batch)
            digests.append("sha256:" + hashlib.sha256(payload).hexdigest())
            execution_ids.append(execution_id)
        seen: set[str] = set()
        for item in combined:
            if item["id"] in seen:
                raise ValueError("production batches contain duplicate item IDs")
            seen.add(item["id"])
        if len(combined) < required_rows:
            raise ValueError("production batches did not reach the accepted-row target")
        retained = combined[:required_rows]
        receipt = {
            "schema": "aar.autodata.native-campaign-consumption/v1",
            "execution_ids": execution_ids,
            "dataset_sha256s": digests,
            "available_rows": len(combined),
            "row_count": len(retained),
            "required_rows": required_rows,
            "generator_model": generator_model,
            "judge_model": judge_model,
            "judge_threshold": judge_threshold,
            "judge_rubric_version": judge_rubric_version,
            "loaded_at_unix": time.time(),
            "consumer_pid": os.getpid(),
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(destination, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(receipt, output, sort_keys=True, indent=2)
            output.write("\n")
        return retained
    finally:
        for path in temporary_receipts:
            path.unlink(missing_ok=True)
