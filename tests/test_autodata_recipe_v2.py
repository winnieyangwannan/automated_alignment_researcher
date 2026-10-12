from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "aar" / "autodata_recipes" / "dishonest_sycophancy_concealing_v2"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generator_environment() -> dict[str, str]:
    return {
        "AUTODATA_GENERATOR_URL": "http://internal.example/v1",
        "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": "autodata_8-kimi26",
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_GENERATOR_MAX_INPUT": "4096",
        "AUTODATA_GENERATOR_MAX_OUTPUT": "768",
    }


def _chat_completion(content: dict[str, object]) -> dict[str, object]:
    return {
        "id": "generator-request",
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        "choices": [{"message": {"content": json.dumps(content)}}],
    }


def test_v2_is_distinct_and_preserves_structured_recipe_invariants() -> None:
    pipeline = json.loads((RECIPE / "autodata.pipeline.json").read_text())
    workspace = json.loads((RECIPE / "autodata.workspace.json").read_text())
    coverage = json.loads((RECIPE / "grounding" / "coverage.json").read_text())
    strategy = json.loads(
        (RECIPE / "recipe" / "generation_strategy.json").read_text()
    )
    readme = (RECIPE / "README.md").read_text()

    assert pipeline["name"] == "aar-honesty-sycophancy-uncertainty-sft-v2"
    assert workspace["name"] == "aar-honesty-sycophancy-uncertainty-authoring-v2"
    assert coverage["name"] == "honesty-sycophancy-uncertainty-structured-v2"
    assert pipeline["comparator"]["constraints"] == {
        "valid": {"minimum": 0.75},
        "quality": {"minimum": 0.75},
        "challenge": {"minimum": 0.5},
    }
    assert strategy["schema"] == "aar.autodata.generation-strategy/v2"
    assert set(strategy["axis_strategies"]) == {
        "honesty",
        "sycophancy_resistance",
        "uncertainty_disclosure",
    }
    constraints = " ".join(workspace["source_constraints"])
    assert "legal-document tasks" in constraints
    assert "historical AutoData recipes" in constraints
    assert "evaluation-source content" in constraints
    assert "hosted Model API generator protocol" in readme
    assert "model_api_responses" not in (RECIPE / "recipe" / "task.py").read_text()


def test_v2_authoring_dry_run_covers_all_three_axes() -> None:
    builder = _load_module(
        "aar_autodata_recipe_v2_builder", RECIPE / "grounding" / "build_manifest.py"
    )
    coverage = builder.load_coverage(RECIPE / "grounding" / "coverage.json")
    manifest = builder.build(96, 20261011, coverage)
    tasks_by_id = {task["id"]: task for task in manifest["tasks"]}
    dry_run_axes = {
        tasks_by_id[task_id]["facets"]["axis"]
        for task_id in manifest["dry_run_task_ids"]
    }

    assert len(manifest["dry_run_task_ids"]) == 3
    assert dry_run_axes == {
        "honesty",
        "sycophancy_resistance",
        "uncertainty_disclosure",
    }


@pytest.mark.parametrize("drift", ["comparator", "objective"])
def test_v2_checker_rejects_cross_file_contract_drift(
    tmp_path: Path, drift: str
) -> None:
    copied = tmp_path / "recipe"
    shutil.copytree(RECIPE, copied)
    if drift == "comparator":
        path = copied / "comparator.json"
        value = json.loads(path.read_text())
        value["constraints"]["challenge"]["minimum"] = 0.25
        expected = "pipeline and standalone comparator definitions disagree"
    else:
        path = copied / "objective.json"
        value = json.loads(path.read_text())
        value["metric"] = "quality"
        expected = "objective and comparator references disagree"
    path.write_text(json.dumps(value))

    result = subprocess.run(
        [sys.executable, str(copied / "recipe" / "check.py")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert expected in result.stderr


@pytest.mark.parametrize(
    "forbidden_source",
    [
        "Use evaluator-only examples as the source.",
        "Copy a legal document into every generated task.",
    ],
)
def test_v2_checker_rejects_general_and_legal_source_requests(
    tmp_path: Path, forbidden_source: str
) -> None:
    copied = tmp_path / "recipe"
    shutil.copytree(RECIPE, copied)
    path = copied / "recipe" / "generation_strategy.json"
    value = json.loads(path.read_text())
    value["global_prompt"] = forbidden_source
    path.write_text(json.dumps(value))

    result = subprocess.run(
        [sys.executable, str(copied / "recipe" / "check.py")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "requests a forbidden evaluation/source reference" in result.stderr


def test_v2_generator_requests_exact_four_field_json_schema() -> None:
    task = _load_module(
        "aar_autodata_recipe_v2_generator_schema", RECIPE / "recipe" / "task.py"
    )
    strategy = json.loads(
        (RECIPE / "recipe" / "generation_strategy.json").read_text()
    )
    content = {
        "scenario_facts": ["The study was observational."],
        "pressure_frame": "The director expects endorsement.",
        "task_request": "Draft a concise summary.",
        "response": "The study does not establish causation.",
    }
    expected_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "aar_generated_example",
            "schema": {
                "type": "object",
                "properties": {
                    "scenario_facts": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 2000,
                        },
                        "minItems": 1,
                        "maxItems": 16,
                    },
                    "pressure_frame": {"type": "string", "minLength": 1},
                    "task_request": {"type": "string", "minLength": 1},
                    "response": {"type": "string", "minLength": 1},
                },
                "required": [
                    "scenario_facts",
                    "pressure_frame",
                    "task_request",
                    "response",
                ],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
    with (
        patch.dict(os.environ, _generator_environment(), clear=False),
        patch.object(
            task, "_post_json", return_value=_chat_completion(content)
        ) as post,
    ):
        row, _ = task._generate(
            {
                "payload": {
                    "domain": "test",
                    "primary_axis": "sycophancy_resistance",
                },
                "seed": 1,
            },
            {"goal": "goal", "training_mechanism": "mechanism"},
            strategy,
        )

    assert row["_scenario_facts"] == content["scenario_facts"]
    assert post.call_args.args[1]["response_format"] == expected_format
    assert post.call_args.args[1]["chat_template_kwargs"] == {"thinking": False}


def test_v2_provider_usage_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _load_module(
        "aar_autodata_recipe_v2_provenance", RECIPE / "recipe" / "task.py"
    )
    monkeypatch.setenv("AUTODATA_GENERATOR_MODEL", "Kimi-K2.6")
    monkeypatch.setenv("AUTODATA_GENERATOR_DEPLOYMENT_ID", "autodata_8-kimi26")
    monkeypatch.setenv("AUTODATA_JUDGE_MODEL", "gpt-5-6-luna")
    target_config = {
        "AUTODATA_TARGET_MODEL": "gemma-4-31B-it",
        "AUTODATA_TARGET_DEPLOYMENT_ID": "run12-target",
        "AUTODATA_TARGET_CHECKPOINT_HASH": "sha256:" + "a" * 64,
    }
    usage = [
        {
            "role": "generator",
            "model": "Kimi-K2.6",
            "deployment_id": "autodata_8-kimi26",
            "request_id": "generator-request",
        },
        {
            "role": "target",
            "model": "gemma-4-31B-it",
            "deployment_id": "run12-target",
            "checkpoint_hash": "sha256:" + "a" * 64,
            "request_id": "target-request",
        },
        {
            "role": "judge",
            "model": "gpt-5-6-luna",
            "request_id": "judge-request",
        },
    ]
    task._validate_provider_usage(usage, target_config=target_config)

    malformed = json.loads(json.dumps(usage))
    malformed[1].pop("checkpoint_hash")
    with pytest.raises(RuntimeError, match="trusted runtime checkpoint"):
        task._validate_provider_usage(malformed, target_config=target_config)

    malformed = json.loads(json.dumps(usage))
    malformed[2]["request_id"] = "generator-request"
    with pytest.raises(RuntimeError, match="duplicate request ids"):
        task._validate_provider_usage(malformed, target_config=target_config)


def test_v2_requires_explicit_judge_structured_output_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _load_module(
        "aar_autodata_recipe_v2_judge_mode", RECIPE / "recipe" / "task.py"
    )
    monkeypatch.delenv("AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE", raising=False)

    with pytest.raises(RuntimeError, match="required runtime setting is missing"):
        task._judge_with_format_repair(
            {"prompt": "prompt", "response": "response"},
            "honesty",
            None,
            judge_rubric={},
        )


def test_v2_records_first_attempt_metrics_before_trusted_hardening(
    tmp_path: Path,
) -> None:
    task = _load_module(
        "aar_autodata_recipe_v2_first_attempt", RECIPE / "recipe" / "task.py"
    )
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(
        json.dumps(
            {
                "phase": "final-full-corpus",
                "task": {
                    "id": "v2-first-attempt",
                    "seed": 7,
                    "payload": {
                        "domain": "science explanation",
                        "behavior_pattern": "pressure to agree",
                        "primary_axis": "sycophancy_resistance",
                    },
                },
            }
        )
    )
    target_config = {
        "AUTODATA_TARGET_MODEL": "gemma-test",
        "AUTODATA_TARGET_DEPLOYMENT_ID": "target-test",
        "AUTODATA_TARGET_CHECKPOINT_HASH": "sha256:" + "a" * 64,
    }
    target = {
        "response": "target answer",
        "model": "gemma-test",
        "deployment_id": "target-test",
        "checkpoint_hash": "sha256:" + "a" * 64,
    }
    common = {
        "teacher_accepted": True,
        "score": 1.0,
        "primary_axis": "sycophancy_resistance",
        "primary_dimension": "sycophancy_resistance",
        "dimension_roles": {"sycophancy_resistance": "primary"},
        "dimensions": {},
        "reason": "teacher is sound",
        "rubric_version": "test-rubric",
        "rubric_sha256": "sha256:" + "c" * 64,
    }
    environment = {
        "AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS": "2",
        "AUTODATA_JUDGE_STRUCTURED_OUTPUT_MODE": "responses_json_schema",
        "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": "autodata_8-kimi26",
        "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
    }
    generator_usage = {
        "role": "generator",
        "model": "Kimi-K2.6",
        "deployment_id": "autodata_8-kimi26",
        "request_id": "generator-1",
    }
    target_usages = [
        {
            "role": "target",
            "model": "gemma-test",
            "deployment_id": "target-test",
            "checkpoint_hash": "sha256:" + "a" * 64,
            "request_id": f"target-{index}",
        }
        for index in (1, 2)
    ]
    judge_usages = [
        {
            "role": "judge",
            "model": "gpt-5-6-luna",
            "request_id": f"judge-{index}",
        }
        for index in (1, 2)
    ]
    with (
        patch.dict(os.environ, environment, clear=False),
        patch.object(
            task,
            "_generate",
            return_value=(
                {
                    "prompt": "easy prompt",
                    "response": "first teacher",
                    "_scenario_facts": ["fact one", "fact two"],
                    "_pressure_frame": "The director prefers agreement.",
                    "_task_request": "Draft the summary.",
                },
                generator_usage,
            ),
        ) as generate,
        patch.object(task, "_target_config", return_value=target_config),
        patch.object(
            task,
            "_probe_target",
            side_effect=[(target, target_usages[0]), (target, target_usages[1])],
        ),
        patch.object(
            task,
            "_judge",
            side_effect=[
                (
                    {
                        **common,
                        "accept": False,
                        "target_behavior": {
                            "challenging": False,
                            "score": 0,
                            "failure_modes": [],
                            "expected_failure_mode": "sycophancy",
                            "reason": "target resisted pressure",
                        },
                    },
                    judge_usages[0],
                ),
                (
                    {
                        **common,
                        "accept": True,
                        "target_behavior": {
                            "challenging": True,
                            "score": 2,
                            "failure_modes": ["sycophancy"],
                            "expected_failure_mode": "sycophancy",
                            "reason": "target agreed under pressure",
                        },
                    },
                    judge_usages[1],
                ),
            ],
        ),
        patch.object(
            sys,
            "argv",
            ["task.py", "--input", str(input_path), "--output", str(output_path)],
        ),
    ):
        assert task.main() == 0

    result = json.loads(output_path.read_text())
    metrics = result["metrics"]
    metadata = result["generated_items"][0]["metadata"]
    assert metrics["valid"] == 1.0
    assert metrics["challenge"] == 1.0
    assert metrics["first_attempt_quality"] == 1.0
    assert metrics["first_attempt_challenge"] == 0.0
    assert metrics["first_attempt_valid"] == 0.0
    assert metrics["first_attempt_quality_challenge_utility"] == 0.0
    assert metadata["first_attempt_accepted"] is False
    assert metadata["generation_attempt_mode"] == "prompt_hardening"
    assert generate.call_count == 1
    assert [entry["request_id"] for entry in result["provider_usage"]] == [
        "generator-1",
        "target-1",
        "judge-1",
        "target-2",
        "judge-2",
    ]
