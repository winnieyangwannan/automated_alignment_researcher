from __future__ import annotations

import json
from pathlib import Path

import pytest

from aar.infrastructure.autodata_contract import (
    training_data_contract_from_campaign_policy,
    validate_generation_inputs,
    validate_training_data_contract,
)

RUBRIC = {
    "version": "run9-axis-conditioned-v3",
    "sha256": "sha256:" + "c" * 64,
}


def _contract(objective: str = "sft") -> dict:
    return {
        "schema": "aar.autodata.training-data-contract/v1",
        "training_objective": objective,
        "required_item_fields": (
            ["prompt", "response"]
            if objective == "sft"
            else ["prompt", "chosen", "rejected"]
        ),
        "required_rows": 1000,
        "minimum_successful_task_fraction": 0.95,
        "judge_rubric": RUBRIC,
        "generator": {"model": "Kimi-K2.6", "deployment_id": "kimi"},
        "judge": {"model": "gpt-5-6-luna"},
        "target": {
            "required": True,
            "model": "gemma",
            "deployment_id": "gemma-base",
            "checkpoint_hash": "sha256:" + "a" * 64,
        },
    }


def _policy() -> dict:
    return {
        "required_solve_env": {
            "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
            "AUTODATA_GENERATOR_DEPLOYMENT_ID": "kimi",
            "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
            "AUTODATA_TARGET_ENABLED": "1",
            "AUTODATA_TARGET_MODEL": "gemma",
            "AUTODATA_TARGET_DEPLOYMENT_ID": "gemma-base",
            "AUTODATA_TARGET_CHECKPOINT_HASH": "sha256:" + "a" * 64,
        }
    }


def test_contract_accepts_sft_and_dpo_and_rejects_wrong_schema() -> None:
    assert validate_training_data_contract(_contract())["training_objective"] == "sft"
    assert (
        validate_training_data_contract(_contract("dpo"))["training_objective"] == "dpo"
    )
    broken = _contract("dpo")
    broken["required_item_fields"] = ["prompt", "response"]
    with pytest.raises(ValueError, match="do not match"):
        validate_training_data_contract(broken)


def test_contract_is_derived_from_the_iteration_campaign_policy() -> None:
    contract = training_data_contract_from_campaign_policy(
        _policy(),
        required_rows=1000,
        minimum_successful_task_fraction=0.95,
        judge_rubric=RUBRIC,
    )

    assert contract == _contract()


def test_generation_inputs_bind_contract_policy_pipeline_and_finalization(
    tmp_path: Path,
) -> None:
    contract = _contract()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract))
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(_policy()))
    pipeline = tmp_path / "pipeline" / "autodata.pipeline.json"
    pipeline.parent.mkdir()
    pipeline.write_text("{}")
    (pipeline.parent / "training-data-contract.json").write_text(json.dumps(contract))
    execution = tmp_path / "production.execution.json"
    execution.write_text(
        json.dumps(
            {
                "mode": "production",
                "concurrency": 32,
                "finalization": {
                    "minimum_generated_items": 1000,
                    "minimum_successful_task_fraction": 0.95,
                },
            }
        )
    )

    assert (
        validate_generation_inputs(
            pipeline_manifest=pipeline,
            execution_manifest=execution,
            contract_path=contract_path,
            campaign_policy_path=policy_path,
            expected_concurrency=32,
        )["required_rows"]
        == 1000
    )

    value = json.loads(execution.read_text())
    value["finalization"]["minimum_generated_items"] = 1250
    execution.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="accepted-row target"):
        validate_generation_inputs(
            pipeline_manifest=pipeline,
            execution_manifest=execution,
            contract_path=contract_path,
            campaign_policy_path=policy_path,
            expected_concurrency=32,
        )

    value = json.loads(execution.read_text())
    value["finalization"]["minimum_generated_items"] = 1000
    value["concurrency"] = 8
    execution.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="operator runtime profile"):
        validate_generation_inputs(
            pipeline_manifest=pipeline,
            execution_manifest=execution,
            contract_path=contract_path,
            campaign_policy_path=policy_path,
            expected_concurrency=32,
        )
