from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECIPE = (
    ROOT
    / "aar"
    / "autodata_recipes"
    / "dishonest_sycophancy_concealing_v1"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v1_recipe_is_independent_and_selectable() -> None:
    assert RECIPE.is_dir()
    assert (
        ROOT
        / "aar"
        / "autodata_recipes"
        / "dishonest_sycophancy_concealing"
    ).is_dir()
    readme = (RECIPE / "README.md").read_text(encoding="utf-8")
    assert (
        "recipe_root: "
        "aar/autodata_recipes/dishonest_sycophancy_concealing_v1"
    ) in readme


def test_v1_recipe_check_and_comparator_contract() -> None:
    subprocess.run(
        [sys.executable, str(RECIPE / "recipe" / "check.py")],
        cwd=RECIPE,
        check=True,
    )
    pipeline = json.loads((RECIPE / "autodata.pipeline.json").read_text())
    comparator = json.loads((RECIPE / "comparator.json").read_text())
    assert pipeline["mutable_paths"] == ["recipe/generation_strategy.json"]
    assert pipeline["comparator"]["constraints"] == {
        "valid": {"minimum": 0.75}
    }
    assert comparator["constraints"] == pipeline["comparator"]["constraints"]


def test_v1_generator_usage_binds_runtime_deployment(monkeypatch) -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_generator_provenance",
        RECIPE / "recipe" / "task.py",
    )
    environment = {
        "AUTODATA_GENERATOR_URL": "http://internal.example/v1",
        "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
        "AUTODATA_GENERATOR_DEPLOYMENT_ID": "autodata_8-kimi26",
        "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
        "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
        "AUTODATA_GENERATOR_MAX_INPUT": "4096",
        "AUTODATA_GENERATOR_MAX_OUTPUT": "768",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        task,
        "_post_json",
        lambda *args, **kwargs: {
            "id": "generator-request",
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"prompt": "prompt", "response": "response"}
                        )
                    }
                }
            ],
        },
    )

    _, usage = task._generate(
        {"payload": {"domain": "test"}, "seed": 1},
        {"goal": "goal", "training_mechanism": "mechanism"},
        {
            "system_prompt": "system",
            "scenario_prompt_prefix": "prefix",
            "temperature": 0.2,
        },
    )

    assert usage["role"] == "generator"
    assert usage["model"] == "Kimi-K2.6"
    assert usage["request_id"] == "generator-request"
    assert usage["deployment_id"] == "autodata_8-kimi26"


def test_v1_task_fails_fast_on_incomplete_provider_provenance(monkeypatch) -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_provenance_validation",
        RECIPE / "recipe" / "task.py",
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

    mutations = {
        "missing role": (lambda value: value.pop(1), "missing a required role"),
        "missing request id": (
            lambda value: value[0].pop("request_id"),
            "incomplete provider identity",
        ),
        "duplicate request id": (
            lambda value: value[1].update(request_id="generator-request"),
            "duplicate request ids",
        ),
        "generator deployment": (
            lambda value: value[0].pop("deployment_id"),
            "generator usage.*runtime deployment",
        ),
        "target checkpoint": (
            lambda value: value[1].pop("checkpoint_hash"),
            "target usage.*runtime checkpoint",
        ),
        "judge model": (
            lambda value: value[2].update(model="unexpected-judge"),
            "judge usage.*runtime model",
        ),
    }
    for mutate, error in mutations.values():
        malformed = json.loads(json.dumps(usage))
        mutate(malformed)
        with pytest.raises(RuntimeError, match=error):
            task._validate_provider_usage(malformed, target_config=target_config)


def test_v1_grounding_is_small_broad_and_axis_stratified() -> None:
    builder = _load_module(
        "aar_autodata_recipe_v1_builder",
        RECIPE / "grounding" / "build_manifest.py",
    )
    coverage = builder.load_coverage(RECIPE / "grounding" / "coverage.json")
    manifest = builder.build(6, 20261008, coverage)
    assert coverage["minimum_task_count"] == 6
    assert len(coverage["behavior_patterns"]) == 6
    assert len(manifest["dry_run_task_ids"]) == 3
    dry_run = manifest["tasks"][:3]
    assert {task["facets"]["axis"] for task in dry_run} == {
        "honesty",
        "sycophancy_resistance",
        "uncertainty_disclosure",
    }


def test_v1_meta_scores_first_attempt_and_production_may_repair(
    monkeypatch,
) -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_task",
        RECIPE / "recipe" / "task.py",
    )
    monkeypatch.setenv("AUTODATA_TARGET_FEEDBACK_MAX_ATTEMPTS", "5")
    assert task._generation_attempt_limit(
        "baseline-visible", target_configured=True
    ) == 1
    assert task._generation_attempt_limit(
        "selection-hidden-r0", target_configured=True
    ) == 1
    assert task._generation_attempt_limit(
        "final-full-corpus", target_configured=True
    ) == 5
    assert task._generation_attempt_limit(
        "final-full-corpus-retry-1", target_configured=True
    ) == 5
    assert task._generation_attempt_limit(
        "final-full-corpus", target_configured=False
    ) == 1


def test_v1_feedback_does_not_expose_raw_target_answer() -> None:
    task = _load_module(
        "aar_autodata_recipe_v1_feedback",
        RECIPE / "recipe" / "task.py",
    )
    feedback = task._retry_feedback(
        {"prompt": "prompt", "response": "teacher"},
        {
            "teacher_accepted": False,
            "reason": "teacher reason",
            "target_behavior": {
                "challenging": True,
                "reason": "target reason",
            },
        },
    )
    assert "target_response" not in feedback
    assert feedback["target_challenging"] is True
