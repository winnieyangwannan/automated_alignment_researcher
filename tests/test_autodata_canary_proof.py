from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from aar.autodata_campaign_policy import create_base_target_manifest
from scripts.verify_autodata_canary_proof import verify_proof


GENERATOR_MODEL = "Kimi-K2.6"
GENERATOR_DEPLOYMENT = "autodata_8-kimi26"
JUDGE_MODEL = "gpt-5-6-luna"
TARGET_MODEL = "gemma-4-31B-it"
TARGET_DEPLOYMENT = "trial12-base-target"


def _usage(role: str, model: str, request_id: str) -> dict[str, object]:
    return {
        "request_id": request_id,
        "role": role,
        "model": model,
        "input_tokens": 10,
        "output_tokens": 5,
        "estimated_cost_usd": "0.00003",
        "cost_basis": "operator-configured-token-rates",
    }


def _proof(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, object]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    base = tmp_path / "base"
    base.mkdir()
    (base / "config.json").write_text('{"model_type":"gemma4"}\n')
    (base / "model.safetensors.index.json").write_text('{"weight_map":{}}\n')
    binding = create_base_target_manifest(
        iteration=1,
        chain_id="canary",
        base_checkpoint=base,
        endpoint={
            "url": "http://gateway/v1",
            "host_header": "ram-inference-gateway.ingress.",
            "model": TARGET_MODEL,
            "deployment_id": TARGET_DEPLOYMENT,
        },
    )
    (tmp_path / "target-binding.json").write_text(json.dumps(binding))
    preflight = {
        "success": True,
        "target_model": TARGET_MODEL,
        "target_deployment_id": TARGET_DEPLOYMENT,
        "target_checkpoint_hash": binding["checkpoint_hash"],
        "target_iteration": 1,
        "target_incumbent_run_id": None,
    }
    (tmp_path / "preflight.json").write_text(json.dumps(preflight))
    generator = _usage("generator", GENERATOR_MODEL, "generator-request")
    generator["deployment_id"] = GENERATOR_DEPLOYMENT
    target = _usage("target", TARGET_MODEL, "target-request")
    target["deployment_id"] = TARGET_DEPLOYMENT
    target["checkpoint_hash"] = binding["checkpoint_hash"]
    judge = _usage("judge", JUDGE_MODEL, "judge-request")
    report = {
        "success": True,
        "broker_status": "SUCCEEDED",
        "task_result_outcome": "succeeded",
        "task_result_schema_valid": True,
        "provider_call_count": 3,
        "generator_deployment_id": GENERATOR_DEPLOYMENT,
        "provider_usage": [generator, target, judge],
        "target_model": TARGET_MODEL,
        "target_deployment_id": TARGET_DEPLOYMENT,
        "target_binding_checkpoint_hash": binding["checkpoint_hash"],
        "target_iteration": 1,
        "target_incumbent_run_id": None,
    }
    (tmp_path / "canary-report.json").write_text(json.dumps(report))
    return tmp_path, preflight, report


def _verify(root: Path) -> dict[str, object]:
    return verify_proof(
        root,
        generator_model=GENERATOR_MODEL,
        generator_deployment_id=GENERATOR_DEPLOYMENT,
        judge_model=JUDGE_MODEL,
        expected_target_deployment_id=TARGET_DEPLOYMENT,
    )


def test_canary_proof_binds_all_current_provider_identities(tmp_path: Path) -> None:
    root, _, report = _proof(tmp_path)
    report["provider_usage"].append(
        _usage("judge", JUDGE_MODEL, "judge-repair-request")
    )
    report["provider_call_count"] = 4
    (root / "canary-report.json").write_text(json.dumps(report))

    summary = _verify(root)

    assert summary["success"] is True
    assert summary["provider_call_count"] == 4


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("count", "provider-call count is inconsistent"),
        ("generator_deployment", "generator deployment is inconsistent"),
        ("target_checkpoint", "target checkpoint is inconsistent"),
        ("judge_field", "judge usage fields are invalid"),
        ("duplicate_request", "provider request ids are not unique"),
    ],
)
def test_canary_proof_rejects_provider_drift(
    tmp_path: Path, mutation: str, message: str
) -> None:
    root, _, original = _proof(tmp_path)
    report = copy.deepcopy(original)
    usage = report["provider_usage"]
    if mutation == "count":
        report["provider_call_count"] = 4
    elif mutation == "generator_deployment":
        usage[0]["deployment_id"] = "wrong-generator"
    elif mutation == "target_checkpoint":
        usage[1]["checkpoint_hash"] = "sha256:" + "b" * 64
    elif mutation == "judge_field":
        usage[2]["deployment_id"] = "unexpected"
    else:
        usage[2]["request_id"] = usage[0]["request_id"]
    (root / "canary-report.json").write_text(json.dumps(report))

    with pytest.raises(RuntimeError, match=message):
        _verify(root)


def test_canary_proof_rejects_preflight_or_requested_target_drift(
    tmp_path: Path,
) -> None:
    root, preflight, _ = _proof(tmp_path)
    preflight["target_deployment_id"] = "wrong-target"
    (root / "preflight.json").write_text(json.dumps(preflight))
    with pytest.raises(RuntimeError, match="preflight target_deployment_id"):
        _verify(root)

    root, _, _ = _proof(tmp_path / "second")
    with pytest.raises(RuntimeError, match="requested deployment"):
        verify_proof(
            root,
            generator_model=GENERATOR_MODEL,
            generator_deployment_id=GENERATOR_DEPLOYMENT,
            judge_model=JUDGE_MODEL,
            expected_target_deployment_id="different-target",
        )
