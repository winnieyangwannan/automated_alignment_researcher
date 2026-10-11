from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aar.infrastructure.autodata_execution_contract import (
    canonical_execution_manifest,
    canonical_production_manifest_from_meta,
    operator_execution_settings,
    validate_runtime_campaign_policy_rewrite,
)


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _policy() -> dict[str, object]:
    return {
        "max_cost_usd": "41775",
        "environment": "oci-runner-firecracker-large",
        "image": "python@sha256:" + "a" * 64,
        "expected_image_id": "b" * 64,
        "max_cpus": 2,
        "max_memory_mb": 2048,
        "required_solve_env": {
            "AUTODATA_TARGET_ENABLED": "1",
            "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "1",
            "AUTODATA_JUDGE_FORMAT_MAX_ATTEMPTS": "2",
            "AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE": "responses_json_schema",
        },
    }


def _settings() -> dict[str, object]:
    return {
        "meta": {
            "maximum_iterations": 3,
            "minimum_iterations": 3,
            "early_stop_patience": 3,
            "tuning_tasks": 64,
            "validation_tasks": 32,
            "test_tasks": 32,
        },
        "production": {
            "initial_tasks": 1250,
            "required_rows": 1000,
            "minimum_successful_task_fraction": 0.95,
        },
        "concurrency": 32,
        "campaign_policy": _policy(),
        "broker_url": "http://127.0.0.1:12345",
        "meta_wall_seconds": 604800,
        "production_wall_seconds": 604800,
        "meta_evaluation_attempts": 608,
        "meta_finalization_retry_attempts": 96,
        "meta_model_task_attempts": 704,
        "meta_task_attempts": 707,
        "production_task_attempts": 2500,
    }


def _executor() -> dict[str, object]:
    policy = _policy()
    return {
        "kind": "sandoq-firecracker",
        "environment": policy["environment"],
        "image": policy["image"],
        "expected_image_id": policy["expected_image_id"],
        "broker_url": "http://127.0.0.1:12345",
        "broker_auth_secret_ref": "AAR_AUTODATA_CAPABILITY",
        "model_backed": True,
        "cpus": 2,
        "memory_mb": 2048,
        "network": "host",
        "workdir": "/workspace",
        "non_secret_env": policy["required_solve_env"],
    }


def test_operator_settings_come_from_resolved_config() -> None:
    resolved = {
        "run": {
            "meta_optimization": {
                "maximum_iterations": 3,
                "minimum_iterations": 3,
                "early_stop_patience": 3,
                "tuning_tasks": 64,
                "validation_tasks": 32,
                "test_tasks": 32,
            },
            "production": {
                "initial_tasks": 1250,
                "required_rows": 1000,
                "minimum_successful_task_fraction": 0.95,
            },
            "generation": {
                "target_feedback_max_attempts": 5,
                "judge_format_max_attempts": 2,
                "judge_structured_output_mode": "responses_json_schema",
            },
            "recipe_root": ("aar/autodata_recipes/dishonest_sycophancy_concealing_v1"),
            "stage_timing": {"native_schema_wall_seconds": 604800},
        },
        "profile": {
            "execution": {"concurrency_per_chain": 32},
            "providers": {
                "generator": {
                    "max_input_tokens": 196608,
                    "max_output_tokens": 65536,
                    "input_usd_per_million": "1",
                    "output_usd_per_million": "4",
                },
                "judge": {
                    "max_input_tokens": 1000000,
                    "max_output_tokens": 65536,
                    "input_usd_per_million": "1",
                    "output_usd_per_million": "4",
                },
                "target": {
                    "max_input_tokens": 196608,
                    "max_output_tokens": 65536,
                    "input_usd_per_million": "0",
                    "output_usd_per_million": "0",
                },
            },
        },
    }
    settings = operator_execution_settings(
        resolved,
        campaign_policy=_policy(),
        training_data_contract={
            "required_rows": 1000,
            "minimum_successful_task_fraction": 0.95,
        },
    )

    assert settings["meta"] == {
        "maximum_iterations": 3,
        "minimum_iterations": 3,
        "early_stop_patience": 3,
        "tuning_tasks": 64,
        "validation_tasks": 32,
        "test_tasks": 32,
    }
    assert settings["concurrency"] == 32
    assert settings["meta_evaluation_attempts"] == 608
    assert settings["meta_finalization_retry_attempts"] == 96
    assert settings["meta_model_task_attempts"] == 704
    assert settings["required_campaign_task_attempts"] == 3204
    assert settings["required_campaign_round_reservations"] == 14004
    assert settings["required_campaign_cost_usd"] == "41774.49216"
    assert settings["required_judge_calls"] == 28008
    assert settings["authoring_model_task_attempts"] == 32
    assert settings["finalization_model_rounds_per_task"] == 5

    truncated_retry = json.loads(json.dumps(_policy()))
    truncated_retry["max_cost_usd"] = "41774.492159"
    with pytest.raises(
        ValueError,
        match="including authoring and finalization feedback",
    ):
        operator_execution_settings(
            resolved,
            campaign_policy=truncated_retry,
            training_data_contract={
                "required_rows": 1000,
                "minimum_successful_task_fraction": 0.95,
            },
        )

    insufficient = json.loads(json.dumps(_policy()))
    insufficient["max_cost_usd"] = "299"
    with pytest.raises(ValueError, match="requires at least 41774.49216"):
        operator_execution_settings(
            resolved,
            campaign_policy=insufficient,
            training_data_contract={
                "required_rows": 1000,
                "minimum_successful_task_fraction": 0.95,
            },
        )


def test_runtime_campaign_accepts_only_loopback_generator_rewrite() -> None:
    compiled = _policy()
    compiled["required_solve_env"] = {
        "AUTODATA_GENERATOR_URL": "http://cluster-ingress/v1",
        "AUTODATA_GENERATOR_HOST_HEADER": "gateway.internal",
        "AUTODATA_TARGET_ENABLED": "1",
    }
    runtime = json.loads(json.dumps(compiled))
    runtime["required_solve_env"][
        "AUTODATA_GENERATOR_URL"
    ] = "http://127.0.0.1:54321/v1"
    runtime["required_solve_env"]["AUTODATA_GENERATOR_HOST_HEADER"] = ""

    checked = validate_runtime_campaign_policy_rewrite(compiled, runtime)
    assert (
        checked["required_solve_env"]["AUTODATA_GENERATOR_URL"]
        == "http://127.0.0.1:54321/v1"
    )

    mutated = json.loads(json.dumps(runtime))
    mutated["max_cpus"] = 64
    with pytest.raises(ValueError, match="outside required_solve_env"):
        validate_runtime_campaign_policy_rewrite(compiled, mutated)

    mutated = json.loads(json.dumps(runtime))
    mutated["required_solve_env"]["AUTODATA_TARGET_ENABLED"] = "0"
    with pytest.raises(ValueError, match="unauthorized mutation"):
        validate_runtime_campaign_policy_rewrite(compiled, mutated)


def _meta_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    pipeline = _write_json(tmp_path / "pipeline" / "autodata.pipeline.json", {})
    ids = [f"task-{index:03d}" for index in range(128)]
    grounding = _write_json(
        pipeline.parent / "grounding" / "meta.json",
        {
            "schema": "autodata.grounding/v1",
            "tasks": [{"id": task_id} for task_id in ids[:96]],
        },
    )
    test_grounding = _write_json(
        pipeline.parent / "grounding" / "test.json",
        {
            "schema": "autodata.grounding/v1",
            "tasks": [{"id": task_id} for task_id in ids[96:]],
        },
    )
    reference = {
        "manifest_path": "grounding/meta.json",
        "digest": _digest(grounding),
    }
    proposed: dict[str, object] = {
        "schema": "autodata.execution/v1",
        "mode": "meta_optimize",
        "grounding": reference,
        "test_grounding": {
            "manifest_path": "grounding/test.json",
            "digest": _digest(test_grounding),
        },
        "split_seed": int(_digest(grounding).removeprefix("sha256:")[:8], 16),
        "executor": _executor(),
        "budget": {
            "max_iterations": 3,
            "min_iterations": 3,
            "early_stop_patience": 3,
            "max_task_attempts": 707,
            "max_wall_seconds": 604800,
        },
        "concurrency": 32,
        "secret_references": ["AAR_AUTODATA_CAPABILITY"],
        "tuning_task_ids": ids[:64],
        "validation_task_ids": ids[64:96],
    }
    execution = _write_json(tmp_path / "meta.execution.json", proposed)
    return pipeline, execution, proposed


def test_constructs_canonical_three_iteration_meta_manifest(tmp_path: Path) -> None:
    pipeline, execution, proposed = _meta_fixture(tmp_path)

    first = canonical_execution_manifest(
        proposed_manifest=execution,
        pipeline_manifest=pipeline,
        settings=_settings(),
    )
    second = canonical_execution_manifest(
        proposed_manifest=execution,
        pipeline_manifest=pipeline,
        settings=_settings(),
    )

    assert first == second == proposed
    assert first["budget"]["max_iterations"] == 3
    assert len(first["tuning_task_ids"]) == 64
    assert len(first["validation_task_ids"]) == 32


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["budget"].update(max_iterations=1), "max_iterations"),
        (lambda value: value["budget"].update(min_iterations=0), "min_iterations"),
        (
            lambda value: value["budget"].update(early_stop_patience=None),
            "early_stop_patience",
        ),
        (lambda value: value.update(tuning_task_ids=[]), "tuning_task_ids"),
        (lambda value: value.update(validation_task_ids=[]), "validation_task_ids"),
    ],
)
def test_rejects_default_or_wrong_meta_control_values(
    tmp_path: Path, mutation: object, message: str
) -> None:
    pipeline, execution, proposed = _meta_fixture(tmp_path)
    mutation(proposed)  # type: ignore[operator]
    execution.write_text(json.dumps(proposed), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        canonical_execution_manifest(
            proposed_manifest=execution,
            pipeline_manifest=pipeline,
            settings=_settings(),
        )


def test_rejects_grounding_digest_and_partition_overlap(tmp_path: Path) -> None:
    pipeline, execution, proposed = _meta_fixture(tmp_path)
    proposed["grounding"]["digest"] = "sha256:" + "0" * 64  # type: ignore[index]
    execution.write_text(json.dumps(proposed), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        canonical_execution_manifest(
            proposed_manifest=execution,
            pipeline_manifest=pipeline,
            settings=_settings(),
        )


def test_rejects_shared_meta_and_test_manifest(tmp_path: Path) -> None:
    pipeline, execution, proposed = _meta_fixture(tmp_path)
    proposed["test_grounding"] = proposed["grounding"]
    execution.write_text(json.dumps(proposed), encoding="utf-8")

    with pytest.raises(ValueError, match="separate manifests"):
        canonical_execution_manifest(
            proposed_manifest=execution,
            pipeline_manifest=pipeline,
            settings=_settings(),
        )


def test_rejects_unknown_fields_and_wrong_task_attempt_capacity(tmp_path: Path) -> None:
    pipeline, execution, proposed = _meta_fixture(tmp_path)
    proposed["researcher_note"] = "shrink this run"
    execution.write_text(json.dumps(proposed), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown or missing fields"):
        canonical_execution_manifest(
            proposed_manifest=execution,
            pipeline_manifest=pipeline,
            settings=_settings(),
        )

    pipeline, execution, proposed = _meta_fixture(tmp_path / "capacity")
    proposed["budget"]["max_task_attempts"] = 256
    execution.write_text(json.dumps(proposed), encoding="utf-8")
    with pytest.raises(ValueError, match="max_task_attempts"):
        canonical_execution_manifest(
            proposed_manifest=execution,
            pipeline_manifest=pipeline,
            settings=_settings(),
        )

    pipeline, execution, proposed = _meta_fixture(tmp_path / "overlap")
    proposed["validation_task_ids"][0] = proposed["tuning_task_ids"][0]  # type: ignore[index]
    execution.write_text(json.dumps(proposed), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical partition"):
        canonical_execution_manifest(
            proposed_manifest=execution,
            pipeline_manifest=pipeline,
            settings=_settings(),
        )


def test_production_requires_contract_thresholds_and_disjoint_source(
    tmp_path: Path,
) -> None:
    pipeline = _write_json(tmp_path / "pipeline" / "autodata.pipeline.json", {})
    ids = [f"production-{index:04d}" for index in range(1250)]
    grounding = _write_json(
        pipeline.parent / "grounding" / "production-manifest.json",
        {
            "schema": "autodata.grounding/v1",
            "tasks": [{"id": task_id} for task_id in ids],
        },
    )
    execution = _write_json(
        tmp_path / "production.execution.json",
        {
            "schema": "autodata.execution/v1",
            "mode": "production",
            "grounding": {
                "manifest_path": "grounding/production-manifest.json",
                "digest": _digest(grounding),
            },
            "executor": _executor(),
            "split_seed": int(_digest(grounding).removeprefix("sha256:")[:8], 16),
            "budget": {
                "max_iterations": 0,
                "max_task_attempts": 2500,
                "max_wall_seconds": 604800,
            },
            "concurrency": 32,
            "secret_references": ["AAR_AUTODATA_CAPABILITY"],
            "finalization": {
                "minimum_generated_items": 1000,
                "minimum_successful_task_fraction": 0.95,
            },
        },
    )

    canonical = canonical_execution_manifest(
        proposed_manifest=execution,
        pipeline_manifest=pipeline,
        settings=_settings(),
    )
    assert canonical["finalization"]["minimum_generated_items"] == 1000

    native_replay = json.loads(execution.read_text(encoding="utf-8"))
    native_replay["budget"].update(
        min_iterations=0,
        early_stop_patience=None,
    )
    execution.write_text(json.dumps(native_replay), encoding="utf-8")
    replayed = canonical_execution_manifest(
        proposed_manifest=execution,
        pipeline_manifest=pipeline,
        settings=_settings(),
    )
    assert replayed["budget"] == canonical["budget"]

    with pytest.raises(ValueError, match="overlaps meta"):
        canonical_execution_manifest(
            proposed_manifest=execution,
            pipeline_manifest=pipeline,
            settings=_settings(),
            reserved_task_ids=[ids[0]],
        )

    value = json.loads(execution.read_text(encoding="utf-8"))
    value["finalization"]["minimum_generated_items"] = 999
    execution.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="finalization"):
        canonical_execution_manifest(
            proposed_manifest=execution,
            pipeline_manifest=pipeline,
            settings=_settings(),
        )


def test_trusted_orchestration_constructs_production_without_model_manifest(
    tmp_path: Path,
) -> None:
    pipeline = _write_json(tmp_path / "winner" / "autodata.pipeline.json", {})
    ids = [f"safety-prod-{index:04d}" for index in range(1, 1251)]
    grounding = _write_json(
        pipeline.parent / "grounding" / "production-manifest.json",
        {
            "schema": "autodata.grounding/v1",
            "tasks": [{"id": task_id} for task_id in ids],
        },
    )
    reference = {
        "manifest_path": "grounding/production-manifest.json",
        "digest": _digest(grounding),
    }

    manifest = canonical_production_manifest_from_meta(
        meta_manifest={
            "executor": _executor(),
            "secret_references": ["AAR_AUTODATA_CAPABILITY"],
        },
        pipeline_manifest=pipeline,
        production_grounding=reference,
        settings=_settings(),
        reserved_task_ids=[f"task-{index:03d}" for index in range(128)],
    )

    assert manifest["mode"] == "production"
    assert manifest["budget"] == {
        "max_iterations": 0,
        "max_task_attempts": 2500,
        "max_wall_seconds": 604800,
    }
    assert manifest["finalization"] == {
        "minimum_generated_items": 1000,
        "minimum_successful_task_fraction": 0.95,
    }
    assert manifest["concurrency"] == 32

    with pytest.raises(ValueError, match="overlaps meta"):
        canonical_production_manifest_from_meta(
            meta_manifest={
                "executor": _executor(),
                "secret_references": ["AAR_AUTODATA_CAPABILITY"],
            },
            pipeline_manifest=pipeline,
            production_grounding=reference,
            settings=_settings(),
            reserved_task_ids=[ids[0]],
        )
