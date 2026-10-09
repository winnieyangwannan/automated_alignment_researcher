"""Fail-closed contract validation before AutoData generation starts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

CONTRACT_SCHEMA = "aar.autodata.training-data-contract/v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OBJECTIVES = {
    "sft": ("prompt", "response"),
    "dpo": ("prompt", "chosen", "rejected"),
}


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{where} must be an object")
    return value


def _load(path: Path, where: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{where} must be a regular non-symlink file")
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), where)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{where} is not valid JSON") from error


def contract_sha256(contract: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        contract, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_training_data_contract(
    raw: Mapping[str, Any], *, campaign_policy: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    contract = _object(dict(raw), "training-data contract")
    expected = {
        "schema",
        "training_objective",
        "required_item_fields",
        "required_rows",
        "minimum_successful_task_fraction",
        "judge_rubric_version",
        "generator",
        "judge",
        "target",
    }
    if set(contract) != expected or contract.get("schema") != CONTRACT_SCHEMA:
        raise ValueError("training-data contract has unknown fields or schema")
    objective = contract.get("training_objective")
    if objective not in _OBJECTIVES:
        raise ValueError("training_objective must be sft or dpo")
    if contract.get("required_item_fields") != list(_OBJECTIVES[str(objective)]):
        raise ValueError("required_item_fields do not match the training objective")
    rows = contract.get("required_rows")
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 1:
        raise ValueError("required_rows must be a positive integer")
    fraction = contract.get("minimum_successful_task_fraction")
    if (
        isinstance(fraction, bool)
        or not isinstance(fraction, (int, float))
        or not 0 < float(fraction) <= 1
    ):
        raise ValueError("minimum_successful_task_fraction must be in (0,1]")
    rubric = contract.get("judge_rubric_version")
    if not isinstance(rubric, str) or not rubric.strip():
        raise ValueError("judge_rubric_version must be non-empty")

    generator = _object(contract.get("generator"), "generator provenance")
    if set(generator) != {"model", "deployment_id"} or not all(
        isinstance(generator.get(key), str) and generator[key].strip()
        for key in generator
    ):
        raise ValueError("generator provenance is incomplete")
    judge = _object(contract.get("judge"), "judge provenance")
    if (
        set(judge) != {"model"}
        or not isinstance(judge.get("model"), str)
        or not judge["model"].strip()
    ):
        raise ValueError("judge provenance is incomplete")
    target = _object(contract.get("target"), "target provenance")
    required = target.get("required")
    target_fields = (
        {"required", "model", "deployment_id", "checkpoint_hash"}
        if required is True
        else {"required"}
    )
    if not isinstance(required, bool) or set(target) != target_fields:
        raise ValueError("target provenance does not match target.required")
    if required and (
        not all(
            isinstance(target.get(key), str) and target[key].strip()
            for key in ("model", "deployment_id", "checkpoint_hash")
        )
        or _DIGEST.fullmatch(str(target["checkpoint_hash"])) is None
    ):
        raise ValueError("required target provenance is incomplete")

    if campaign_policy is not None:
        policy = _object(dict(campaign_policy), "campaign policy")
        environment = _object(
            policy.get("required_solve_env"), "campaign required_solve_env"
        )
        expected_env = {
            "AUTODATA_GENERATOR_MODEL": generator["model"],
            "AUTODATA_GENERATOR_DEPLOYMENT_ID": generator["deployment_id"],
            "AUTODATA_JUDGE_MODEL": judge["model"],
            "AUTODATA_TARGET_ENABLED": "1" if required else "0",
        }
        if required:
            expected_env.update(
                {
                    "AUTODATA_TARGET_MODEL": target["model"],
                    "AUTODATA_TARGET_DEPLOYMENT_ID": target["deployment_id"],
                    "AUTODATA_TARGET_CHECKPOINT_HASH": target["checkpoint_hash"],
                }
            )
        for key, value in expected_env.items():
            if environment.get(key) != value:
                raise ValueError(f"campaign policy does not match {key}")
        if not required and any(
            key in environment
            for key in (
                "AUTODATA_TARGET_MODEL",
                "AUTODATA_TARGET_DEPLOYMENT_ID",
                "AUTODATA_TARGET_CHECKPOINT_HASH",
            )
        ):
            raise ValueError("target-disabled campaign retains target provenance")
    return contract


def validate_generation_inputs(
    *,
    pipeline_manifest: Path,
    execution_manifest: Path,
    contract_path: Path,
    campaign_policy_path: Path,
) -> dict[str, Any]:
    """Bind one immutable pipeline/execution to the operator's data contract."""
    contract = validate_training_data_contract(
        _load(contract_path, "trusted training-data contract"),
        campaign_policy=_load(campaign_policy_path, "campaign policy"),
    )
    pipeline_contract = _load(
        pipeline_manifest.resolve(strict=True).parent / "training-data-contract.json",
        "pipeline training-data contract",
    )
    if contract_sha256(pipeline_contract) != contract_sha256(contract):
        raise ValueError(
            "pipeline training-data contract does not match operator policy"
        )
    execution = _load(execution_manifest, "AutoData execution manifest")
    if execution.get("mode") == "production":
        finalization = _object(
            execution.get("finalization"), "production finalization policy"
        )
        if finalization.get("minimum_generated_items") != contract["required_rows"]:
            raise ValueError("production accepted-row target does not match contract")
        if (
            finalization.get("minimum_successful_task_fraction")
            != contract["minimum_successful_task_fraction"]
        ):
            raise ValueError("production task-coverage target does not match contract")
    return contract


def validate_dataset_items(items: Any, contract: Mapping[str, Any]) -> None:
    """Validate actual exported rows against the pre-generation declaration."""
    checked = validate_training_data_contract(contract)
    if not isinstance(items, list) or len(items) < checked["required_rows"]:
        raise ValueError("dataset does not satisfy the contracted row count")
    fields = checked["required_item_fields"]
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise TypeError(f"dataset item {index} is not an object")
        for field in fields:
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"dataset item {index} is missing contracted {field}")
        metadata = _object(item.get("metadata"), f"dataset item {index} metadata")
        if metadata.get("judge_rubric_version") != checked["judge_rubric_version"]:
            raise ValueError("dataset rubric does not match the training-data contract")
        usage = item.get("_autodata_usage")
        if not isinstance(usage, list):
            raise TypeError("dataset item lacks model provenance")
        roles: dict[str, dict[str, Any]] = {}
        for entry in usage:
            if not isinstance(entry, dict) or not isinstance(entry.get("role"), str):
                continue
            role = str(entry["role"])
            if role in roles:
                raise ValueError("dataset item repeats model provenance role")
            roles[role] = entry
        generator = roles.get("generator", {})
        if any(
            generator.get(key) != checked["generator"][key]
            for key in ("model", "deployment_id")
        ):
            raise ValueError("dataset generator provenance does not match contract")
        if roles.get("judge", {}).get("model") != checked["judge"]["model"]:
            raise ValueError("dataset judge provenance does not match contract")
        target = checked["target"]
        if target["required"]:
            actual = roles.get("target", {})
            if any(
                actual.get(key) != target[key]
                for key in ("model", "deployment_id", "checkpoint_hash")
            ):
                raise ValueError("dataset target provenance does not match contract")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--campaign-policy", type=Path, required=True)
    args = parser.parse_args()
    contract = validate_training_data_contract(
        _load(args.contract, "training-data contract"),
        campaign_policy=_load(args.campaign_policy, "campaign policy"),
    )
    print(
        json.dumps({"valid": True, "digest": contract_sha256(contract)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
