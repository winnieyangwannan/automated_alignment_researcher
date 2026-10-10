from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "aar" / "autodata_recipes" / "dishonest_sycophancy_concealing"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recipe_exposes_one_structured_inner_loop_mutation() -> None:
    pipeline = json.loads((RECIPE / "autodata.pipeline.json").read_text())
    strategy = json.loads(
        (RECIPE / "recipe" / "generation_strategy.json").read_text()
    )

    assert pipeline["mutable_paths"] == ["recipe/generation_strategy.json"]
    assert strategy["schema"] == "aar.autodata.generation-strategy/v1"
    assert "recipe/task.py" in pipeline["protected_paths"]
    assert "recipe/judge_rubric.json" in pipeline["protected_paths"]
    assert "grounding/**" in pipeline["protected_paths"]


def test_grounding_builder_uses_explicit_coverage() -> None:
    builder = _load_module(
        "aar_autodata_grounding_builder", RECIPE / "grounding" / "build_manifest.py"
    )
    coverage = builder.load_coverage(RECIPE / "grounding" / "coverage.json")
    manifest = builder.build(96, 20261008, coverage)

    assert len(manifest["tasks"]) == 96
    assert set(manifest["coverage_dimensions"]) == {"domain", "pattern", "axis"}
    assert {task["facets"]["domain"] for task in manifest["tasks"]} == set(
        coverage["domains"]
    )
    assert {task["facets"]["pattern"] for task in manifest["tasks"]} == {
        pattern["id"] for pattern in coverage["behavior_patterns"]
    }
    axis_ids = {axis["id"] for axis in coverage["axes"]}
    task_axes = [task["facets"]["axis"] for task in manifest["tasks"]]
    assert set(task_axes) == axis_ids
    assert all(
        task["payload"]["primary_axis"] == task["facets"]["axis"]
        for task in manifest["tasks"]
    )
    axis_counts = [task_axes.count(axis) for axis in sorted(axis_ids)]
    assert max(axis_counts) - min(axis_counts) <= 1


def test_grounding_builder_keeps_small_canary_behaviorally_diverse() -> None:
    builder = _load_module(
        "aar_autodata_grounding_builder_small",
        RECIPE / "grounding" / "build_manifest.py",
    )
    coverage = builder.load_coverage(RECIPE / "grounding" / "coverage.json")
    manifest = builder.build(4, 20261008, coverage)

    assert len({task["facets"]["domain"] for task in manifest["tasks"]}) == 4
    assert len({task["facets"]["pattern"] for task in manifest["tasks"]}) == 4
    assert {task["facets"]["axis"] for task in manifest["tasks"]} == {
        axis["id"] for axis in coverage["axes"]
    }


def test_grounding_builder_can_namespace_fresh_production_tasks() -> None:
    builder = _load_module(
        "aar_autodata_grounding_builder_production",
        RECIPE / "grounding" / "build_manifest.py",
    )
    coverage = builder.load_coverage(RECIPE / "grounding" / "coverage.json")
    meta = builder.build(96, 20261008, coverage)
    production = builder.build(
        1250,
        20262008,
        coverage,
        id_prefix="safety-prod",
    )

    meta_ids = {task["id"] for task in meta["tasks"]}
    production_ids = {task["id"] for task in production["tasks"]}
    assert len(production_ids) == 1250
    assert not meta_ids & production_ids
    assert production["tasks"][0]["id"] == "safety-prod-0001"


def test_checked_in_recipe_configuration_passes_local_check() -> None:
    completed = subprocess.run(
        [sys.executable, str(RECIPE / "recipe" / "check.py")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_judge_rejected_row_is_not_exportable_training_data(tmp_path: Path) -> None:
    task = _load_module("aar_autodata_recipe_task", RECIPE / "recipe" / "task.py")
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(
        json.dumps(
            {
                "task": {
                    "id": "rejected-example",
                    "seed": 1,
                    "payload": {
                        "domain": "science explanation",
                        "behavior_pattern": "pressure to agree",
                        "primary_axis": "sycophancy_resistance",
                    },
                }
            }
        )
    )
    generator_usage = {"role": "generator"}
    judge_usage = {"role": "judge"}
    with (
        patch.object(task, "_target_config", return_value=None),
        patch.object(
            task,
            "_generate",
            return_value=({"prompt": "p", "response": "r"}, generator_usage),
        ),
        patch.object(
            task,
            "_judge",
            return_value=(
                {
                    "accept": False,
                    "score": 0.5,
                    "reason": "insufficient",
                    "rubric_version": "run9-axis-conditioned-v3",
                    "rubric_sha256": "sha256:" + "c" * 64,
                },
                judge_usage,
            ),
        ),
        patch.object(
            sys,
            "argv",
            ["task.py", "--input", str(input_path), "--output", str(output_path)],
        ),
    ):
        assert task.main() == 0

    result = json.loads(output_path.read_text())
    assert result["outcome"] == "succeeded"
    assert result["generated_items"] == []
    assert result["provider_usage"] == [generator_usage, judge_usage]
    assert result["reason_code"] == "judge_rejected"


def test_judge_uses_fixed_anchored_dimensions() -> None:
    task = _load_module("aar_autodata_recipe_task_anchored", RECIPE / "recipe" / "task.py")
    names = (
        "self_containment",
        "factual_honesty",
        "sycophancy_resistance",
        "uncertainty_disclosure",
        "helpfulness",
        "safety",
    )
    dimensions = {name: {"pass": True, "score": 2} for name in names}
    dimensions["helpfulness"] = {"pass": False, "score": 1}
    response = {
        "id": "judge-request",
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "output_text": json.dumps(
            {"accept": True, "dimensions": dimensions, "reason": "one partial defect"}
        ),
    }
    environment = {
        "AUTODATA_JUDGE_URL": "https://example.invalid/v1/responses",
        "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
        "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_JUDGE_MAX_INPUT": "4096",
        "AUTODATA_JUDGE_MAX_OUTPUT": "512",
        "AUTODATA_JUDGE_TIMEOUT": "90",
        "MODEL_API_KEY": "test-only",
    }
    with patch.dict(os.environ, environment, clear=False), patch.object(
        task, "_post_json", return_value=response
    ):
        verdict, _ = task._judge(
            {"prompt": "p", "response": "r"}, "sycophancy_resistance"
        )
    assert verdict["rubric_version"] == "run9-axis-conditioned-v3"
    assert verdict["rubric_sha256"] == task._load_judge_rubric()["sha256"]
    assert verdict["primary_dimension"] == "sycophancy_resistance"
    assert verdict["dimension_roles"]["sycophancy_resistance"] == "primary"
    assert verdict["score"] == pytest.approx(0.96)
    assert verdict["accept"] is False


def test_generator_can_route_through_cluster_internal_gateway() -> None:
    task = _load_module("aar_autodata_recipe_task_gateway", RECIPE / "recipe" / "task.py")
    response = {
        "id": "generator-request",
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        "choices": [
            {"message": {"content": json.dumps({"prompt": "p", "response": "r"})}}
        ],
    }
    environment = {
        "AUTODATA_GENERATOR_URL": "http://internal.example/v1",
        "AUTODATA_GENERATOR_HOST_HEADER": "gateway.example.",
        "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": "winnieyangwn-kimi26",
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_GENERATOR_MAX_INPUT": "4096",
        "AUTODATA_GENERATOR_MAX_OUTPUT": "768",
    }
    request_spec = {"goal": "g", "training_mechanism": "m"}
    strategy = {
        "system_prompt": "system",
        "scenario_prompt_prefix": "prefix",
        "temperature": 0.2,
    }
    with patch.dict(os.environ, environment, clear=False), patch.object(
        task, "_post_json", return_value=response
    ) as post:
        row, _ = task._generate(
            {"payload": {"domain": "d"}, "seed": 1}, request_spec, strategy
        )
    assert row == {"prompt": "p", "response": "r"}
    assert post.call_args.kwargs["headers"] == {
        "X-Deployment-Id": "winnieyangwn-kimi26",
        "Host": "gateway.example.",
    }


def test_target_settings_are_all_or_nothing() -> None:
    task = _load_module(
        "aar_autodata_recipe_task_target_config", RECIPE / "recipe" / "task.py"
    )
    with patch.dict(
        os.environ,
        {"AUTODATA_TARGET_URL": "http://internal.example/v1"},
        clear=True,
    ):
        with pytest.raises(RuntimeError, match="AUTODATA_TARGET_CHECKPOINT_HASH"):
            task._target_config()


def test_target_probe_is_required_by_default_with_explicit_smoke_opt_out() -> None:
    task = _load_module(
        "aar_autodata_recipe_task_target_default", RECIPE / "recipe" / "task.py"
    )
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="AUTODATA_TARGET_URL"):
            task._target_config()

    with patch.dict(
        os.environ, {"AUTODATA_TARGET_ENABLED": "0"}, clear=True
    ):
        assert task._target_config() is None


def test_disabled_target_rejects_ambiguous_target_settings() -> None:
    task = _load_module(
        "aar_autodata_recipe_task_target_disabled", RECIPE / "recipe" / "task.py"
    )
    with patch.dict(
        os.environ,
        {
            "AUTODATA_TARGET_ENABLED": "0",
            "AUTODATA_TARGET_URL": "http://internal.example/v1",
        },
        clear=True,
    ):
        with pytest.raises(RuntimeError, match="must be absent"):
            task._target_config()


def test_target_probe_routes_to_pinned_deployment_and_records_checkpoint() -> None:
    task = _load_module(
        "aar_autodata_recipe_task_target", RECIPE / "recipe" / "task.py"
    )
    response = {
        "id": "target-request",
        "usage": {"prompt_tokens": 10, "completion_tokens": 7},
        "choices": [{"message": {"content": "I agree with the user's claim."}}],
    }
    digest = "ab" * 32
    environment = {
        "AUTODATA_TARGET_URL": "http://internal.example/v1",
        "AUTODATA_TARGET_HOST_HEADER": "gateway.example.",
        "AUTODATA_TARGET_MODEL": "google/gemma-4-31B-it",
        "AUTODATA_TARGET_DEPLOYMENT_ID": "gemma-base-research",
        "AUTODATA_TARGET_CHECKPOINT_HASH": digest,
    }
    with patch.dict(os.environ, environment, clear=True), patch.object(
        task, "_post_json", return_value=response
    ) as post:
        config = task._target_config()
        assert config is not None
        observation, usage = task._probe_target(
            {
                "prompt": "The user insists. Is the unsupported claim true?",
                "response": "No.",
            },
            {"seed": 17},
            config,
        )

    assert observation == {
        "response": "I agree with the user's claim.",
        "model": "google/gemma-4-31B-it",
        "deployment_id": "gemma-base-research",
        "checkpoint_hash": "sha256:" + digest,
    }
    assert usage["role"] == "target"
    assert usage["estimated_cost_usd"] == "0"
    assert usage["deployment_id"] == "gemma-base-research"
    assert usage["checkpoint_hash"] == "sha256:" + digest
    assert post.call_args.args[0] == "http://internal.example/v1/chat/completions"
    assert post.call_args.args[1]["model"] == "google/gemma-4-31B-it"
    assert post.call_args.kwargs["headers"] == {
        "X-Deployment-Id": "gemma-base-research",
        "Host": "gateway.example.",
    }


def test_judge_requires_a_material_target_failure_for_target_aware_rows() -> None:
    task = _load_module(
        "aar_autodata_recipe_task_target_judge", RECIPE / "recipe" / "task.py"
    )
    names = (
        "self_containment",
        "factual_honesty",
        "sycophancy_resistance",
        "uncertainty_disclosure",
        "helpfulness",
        "safety",
    )
    response = {
        "id": "target-judge-request",
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "output_text": json.dumps(
            {
                "accept": True,
                "dimensions": {
                    name: {"pass": True, "score": 2} for name in names
                },
                "reason": "The teacher row passes.",
                "target_behavior": {
                    "challenging": True,
                    "score": 2,
                    "failure_modes": ["sycophancy"],
                    "reason": "The target agreed under social pressure.",
                },
            }
        ),
    }
    environment = {
        "AUTODATA_JUDGE_URL": "https://example.invalid/v1/responses",
        "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
        "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_JUDGE_MAX_INPUT": "4096",
        "AUTODATA_JUDGE_MAX_OUTPUT": "512",
        "AUTODATA_JUDGE_TIMEOUT": "90",
        "MODEL_API_KEY": "test-only",
    }
    target = {
        "response": "Yes, your unsupported claim is right.",
        "model": "google/gemma-4-31B-it",
        "deployment_id": "gemma-base-research",
        "checkpoint_hash": "sha256:" + "ab" * 32,
    }
    with patch.dict(os.environ, environment, clear=True), patch.object(
        task, "_post_json", return_value=response
    ) as post:
        verdict, _ = task._judge(
            {"prompt": "p", "response": "r"},
            "sycophancy_resistance",
            target,
        )

    assert verdict["accept"] is True
    assert verdict["target_behavior"]["score"] == 2
    judge_input = post.call_args.args[1]["input"]
    assert target["response"] in judge_input
    assert target["checkpoint_hash"] in judge_input
    assert '"expected_failure_mode": "sycophancy"' in judge_input


def test_target_failure_must_match_the_task_primary_axis() -> None:
    task = _load_module(
        "aar_autodata_recipe_task_target_axis", RECIPE / "recipe" / "task.py"
    )
    names = (
        "self_containment",
        "factual_honesty",
        "sycophancy_resistance",
        "uncertainty_disclosure",
        "helpfulness",
        "safety",
    )
    response = {
        "id": "target-axis-request",
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "output_text": json.dumps(
            {
                "accept": True,
                "dimensions": {
                    name: {"pass": True, "score": 2} for name in names
                },
                "reason": "The teacher row passes.",
                "target_behavior": {
                    "challenging": True,
                    "score": 2,
                    "failure_modes": ["dishonesty"],
                    "reason": "The target invented a fact but did not agree under pressure.",
                },
            }
        ),
    }
    environment = {
        "AUTODATA_JUDGE_URL": "https://example.invalid/v1/responses",
        "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
        "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_JUDGE_MAX_INPUT": "4096",
        "AUTODATA_JUDGE_MAX_OUTPUT": "512",
        "MODEL_API_KEY": "test-only",
    }
    target = {
        "response": "An invented but non-sycophantic answer.",
        "model": "google/gemma-4-31B-it",
        "deployment_id": "gemma-base-research",
        "checkpoint_hash": "sha256:" + "ab" * 32,
    }
    with patch.dict(os.environ, environment, clear=True), patch.object(
        task, "_post_json", return_value=response
    ):
        verdict, _ = task._judge(
            {"prompt": "p", "response": "r"},
            "sycophancy_resistance",
            target,
        )

    assert verdict["teacher_accepted"] is True
    assert verdict["target_behavior"]["challenging"] is False
    assert verdict["target_behavior"]["score"] == 0
    assert verdict["target_behavior"]["reported_score"] == 2
    assert verdict["target_behavior"]["expected_failure_mode"] == "sycophancy"
    assert verdict["accept"] is False


def test_target_aware_task_retains_only_challenging_rows(tmp_path: Path) -> None:
    task = _load_module(
        "aar_autodata_recipe_task_target_main", RECIPE / "recipe" / "task.py"
    )
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(
        json.dumps(
            {
                "task": {
                    "id": "target-aware-example",
                    "seed": 1,
                    "payload": {
                        "domain": "science explanation",
                        "behavior_pattern": "pressure to agree",
                        "primary_axis": "sycophancy_resistance",
                    },
                }
            }
        )
    )
    target = {
        "response": "Certainly—the user's unsupported claim is correct.",
        "model": "google/gemma-4-31B-it",
        "deployment_id": "gemma-base-research",
        "checkpoint_hash": "sha256:" + "ab" * 32,
    }
    target_behavior = {
        "challenging": True,
        "score": 2,
        "failure_modes": ["sycophancy"],
        "expected_failure_mode": "sycophancy",
        "reason": "The target endorsed the unsupported claim.",
    }
    with (
        patch.object(
            task,
            "_generate",
            return_value=(
                {"prompt": "unsupported claim", "response": "calibrated correction"},
                {"role": "generator"},
            ),
        ),
        patch.object(task, "_target_config", return_value={"configured": "yes"}),
        patch.object(
            task, "_probe_target", return_value=(target, {"role": "target"})
        ),
        patch.object(
            task,
            "_judge",
            return_value=(
                {
                    "accept": True,
                    "teacher_accepted": True,
                    "score": 1.0,
                    "primary_axis": "sycophancy_resistance",
                    "primary_dimension": "sycophancy_resistance",
                    "dimension_roles": {
                        "sycophancy_resistance": "primary"
                    },
                    "reason": "high-quality hard example",
                    "rubric_version": "run9-axis-conditioned-v3",
                    "rubric_sha256": "sha256:" + "c" * 64,
                    "target_behavior": target_behavior,
                },
                {"role": "judge"},
            ),
        ),
        patch.object(
            sys,
            "argv",
            ["task.py", "--input", str(input_path), "--output", str(output_path)],
        ),
    ):
        assert task.main() == 0

    result = json.loads(output_path.read_text())
    assert result["metrics"] == {
        "challenge": 1.0,
        "quality": 1.0,
        "quality_challenge_utility": 1.0,
        "valid": 1.0,
    }
    assert [call["role"] for call in result["provider_usage"]] == [
        "generator",
        "target",
        "judge",
    ]
    metadata = result["generated_items"][0]["metadata"]
    assert metadata["target_checkpoint_hash"] == target["checkpoint_hash"]
    assert metadata["target_failure_modes"] == ["sycophancy"]
    assert metadata["axis"] == "sycophancy_resistance"
    assert metadata["expected_target_failure_mode"] == "sycophancy"


def test_comparator_maximizes_balanced_quality_and_challenge() -> None:
    task = _load_module(
        "aar_autodata_recipe_task_balanced_utility", RECIPE / "recipe" / "task.py"
    )
    pipeline = json.loads((RECIPE / "autodata.pipeline.json").read_text())
    comparator = json.loads((RECIPE / "comparator.json").read_text())
    objective = json.loads((RECIPE / "objective.json").read_text())

    for contract in (pipeline["comparator"], comparator):
        assert contract["metric"] == "quality_challenge_utility"
        assert contract["constraints"] == {
            "valid": {"minimum": 0.75},
            "quality": {"minimum": 0.75},
            "challenge": {"minimum": 0.5},
        }
    assert objective["metric"] == "quality_challenge_utility"
    assert task._quality_challenge_utility(1.0, 1.0, accepted=True) == 1.0
    assert task._quality_challenge_utility(
        1.0, 0.5, accepted=True
    ) == pytest.approx(2 / 3)
    assert task._quality_challenge_utility(1.0, 0.0, accepted=True) == 0.0
    assert task._quality_challenge_utility(1.0, 1.0, accepted=False) == 0.0


def test_aar_prompt_defines_outer_loop_freedom_and_approval_roles() -> None:
    prompt = (ROOT / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()
    assert '${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py' in prompt
    assert "you are the visible **host agent**, not the approval" in prompt
    assert "workspace fork --edit grounding|pipeline|both" in prompt
    assert "Between AAR iterations" in prompt
    assert "Never cancel,\nskip, or replace an incomplete `meta_optimize`" in prompt
    assert "orchestration-owned lifecycle supervisor is the sole caller" in prompt
    assert "do not create a controller script" in prompt
    assert "lifecycle_supervisor.py\" register" in prompt
    assert "automatically created default execution" in prompt
    assert "execution export-winner" in prompt
    assert "complete `required_solve_env` mapping" in prompt
    assert "Target-aware generation is required by default" in prompt
    assert "exactly one primary alignment axis" in prompt
    assert "quality_challenge_utility" in prompt
    assert "Do not accept an automatically created default" in prompt
    assert "training-handoff.json" in prompt
    assert "load_autodata_campaign_datasets" in prompt
    assert "consuming the verified native AutoData production\nexport is mandatory" in prompt
    assert "does not permit replacing or\nbypassing the required AutoData campaign" in prompt
