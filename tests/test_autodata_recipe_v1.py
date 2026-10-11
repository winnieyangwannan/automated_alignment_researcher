from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


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
