#!/usr/bin/env python3
"""Fail closed unless a retained AutoData canary matches current provider identities."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from aar.autodata_campaign_policy import target_environment_from_manifest


BASE_USAGE_FIELDS = {
    "request_id",
    "role",
    "model",
    "input_tokens",
    "output_tokens",
    "estimated_cost_usd",
    "cost_basis",
}
GENERATOR_USAGE_FIELDS = BASE_USAGE_FIELDS | {"deployment_id"}
TARGET_USAGE_FIELDS = GENERATOR_USAGE_FIELDS | {"checkpoint_hash"}


def _read_object(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"{name} is unreadable") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} must be a JSON object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _validate_usage(call: Any, *, fields: set[str], role: str, model: str) -> None:
    _require(isinstance(call, dict), f"{role} usage is not an object")
    _require(set(call) == fields, f"{role} usage fields are invalid")
    _require(call.get("role") == role, f"{role} usage role is invalid")
    _require(call.get("model") == model, f"{role} usage model is invalid")
    request_id = call.get("request_id")
    _require(
        isinstance(request_id, str) and bool(request_id.strip()),
        f"{role} usage request id is invalid",
    )
    for name in ("input_tokens", "output_tokens"):
        value = call.get(name)
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"{role} usage {name} is invalid",
        )
    _require(
        call.get("cost_basis") == "operator-configured-token-rates",
        f"{role} usage cost basis is invalid",
    )
    try:
        cost = Decimal(call["estimated_cost_usd"])
    except (InvalidOperation, TypeError, ValueError) as error:
        raise RuntimeError(f"{role} usage cost is invalid") from error
    _require(cost.is_finite() and cost >= 0, f"{role} usage cost is invalid")


def verify_proof(
    root: Path,
    *,
    generator_model: str,
    generator_deployment_id: str,
    judge_model: str,
    expected_target_deployment_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    binding_path = root / "target-binding.json"
    binding = _read_object(binding_path, "target binding")
    preflight = _read_object(root / "preflight.json", "endpoint preflight")
    report = _read_object(root / "canary-report.json", "canary report")
    target = target_environment_from_manifest(binding_path)

    expected_target = {
        "model": target["AUTODATA_TARGET_MODEL"],
        "deployment_id": target["AUTODATA_TARGET_DEPLOYMENT_ID"],
        "checkpoint_hash": target["AUTODATA_TARGET_CHECKPOINT_HASH"],
        "iteration": binding["iteration"],
        "incumbent_run_id": binding.get("incumbent_run_id"),
    }
    if expected_target_deployment_id:
        _require(
            expected_target["deployment_id"] == expected_target_deployment_id,
            "proof target deployment does not match the requested deployment",
        )
    _require(preflight.get("success") is True, "endpoint preflight did not succeed")
    for field, expected in (
        ("target_model", expected_target["model"]),
        ("target_deployment_id", expected_target["deployment_id"]),
        ("target_checkpoint_hash", expected_target["checkpoint_hash"]),
        ("target_iteration", expected_target["iteration"]),
        ("target_incumbent_run_id", expected_target["incumbent_run_id"]),
    ):
        _require(preflight.get(field) == expected, f"preflight {field} is inconsistent")

    _require(report.get("success") is True, "canary did not succeed")
    _require(report.get("broker_status") == "SUCCEEDED", "broker did not succeed")
    _require(
        report.get("task_result_outcome") == "succeeded",
        "canary task did not succeed",
    )
    _require(
        report.get("task_result_schema_valid") is True,
        "canary task-result schema is invalid",
    )
    for field, expected in (
        ("generator_deployment_id", generator_deployment_id),
        ("target_model", expected_target["model"]),
        ("target_deployment_id", expected_target["deployment_id"]),
        ("target_binding_checkpoint_hash", expected_target["checkpoint_hash"]),
        ("target_iteration", expected_target["iteration"]),
        ("target_incumbent_run_id", expected_target["incumbent_run_id"]),
    ):
        _require(report.get(field) == expected, f"canary {field} is inconsistent")

    usage = report.get("provider_usage")
    _require(isinstance(usage, list), "canary provider usage is not an array")
    _require(len(usage) in {3, 4}, "canary provider-call count is not bounded")
    _require(
        report.get("provider_call_count") == len(usage),
        "canary provider-call count is inconsistent",
    )
    expected_roles = ["generator", "target", "judge"]
    if len(usage) == 4:
        expected_roles.append("judge")
    _require(
        [call.get("role") if isinstance(call, dict) else None for call in usage]
        == expected_roles,
        "canary provider order is invalid",
    )

    _validate_usage(
        usage[0], fields=GENERATOR_USAGE_FIELDS, role="generator", model=generator_model
    )
    _require(
        usage[0]["deployment_id"] == generator_deployment_id,
        "generator deployment is inconsistent",
    )
    _validate_usage(
        usage[1],
        fields=TARGET_USAGE_FIELDS,
        role="target",
        model=expected_target["model"],
    )
    _require(
        usage[1]["deployment_id"] == expected_target["deployment_id"],
        "target deployment is inconsistent",
    )
    _require(
        usage[1]["checkpoint_hash"] == expected_target["checkpoint_hash"],
        "target checkpoint is inconsistent",
    )
    for call in usage[2:]:
        _validate_usage(call, fields=BASE_USAGE_FIELDS, role="judge", model=judge_model)
    request_ids = [call["request_id"] for call in usage]
    _require(len(set(request_ids)) == len(request_ids), "provider request ids are not unique")

    return {
        "success": True,
        "provider_call_count": len(usage),
        "generator_deployment_id": generator_deployment_id,
        "target_deployment_id": expected_target["deployment_id"],
        "target_checkpoint_hash": expected_target["checkpoint_hash"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--generator-model", required=True)
    parser.add_argument("--generator-deployment-id", required=True)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--expected-target-deployment-id")
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = verify_proof(
        args.root,
        generator_model=args.generator_model,
        generator_deployment_id=args.generator_deployment_id,
        judge_model=args.judge_model,
        expected_target_deployment_id=args.expected_target_deployment_id,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
