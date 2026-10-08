from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


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
                    },
                }
            }
        )
    )
    generator_usage = {"role": "generator"}
    judge_usage = {"role": "judge"}
    with (
        patch.object(
            task,
            "_generate",
            return_value=({"prompt": "p", "response": "r"}, generator_usage),
        ),
        patch.object(
            task,
            "_judge",
            return_value=(
                {"accept": False, "score": 0.5, "reason": "insufficient"},
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


def test_aar_prompt_defines_outer_loop_freedom_and_approval_roles() -> None:
    prompt = (ROOT / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()
    assert '${AAR_AUTODATA_PLUGIN_ROOT}/scripts/autodata.py' in prompt
    assert "you are the visible **host agent**, not the approval" in prompt
    assert "workspace fork --edit grounding|pipeline|both" in prompt
    assert "Between AAR iterations" in prompt
