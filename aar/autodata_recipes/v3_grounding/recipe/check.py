#!/usr/bin/env python3
"""Offline validation of the approved grounding and protected pipeline contracts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import contracts as c


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def check() -> None:
    pipeline = read("autodata.pipeline.json")
    comparator = read("comparator.json")
    objective = read("objective.json")
    strategy = read("recipe/generation_strategy.json")
    request = read("recipe/request.json")
    if pipeline.get("mutable_paths") != ["recipe/generation_strategy.json"]:
        raise ValueError("only generation_strategy.json may be mutable")
    required_protected = {
        "grounding/**",
        "schemas/**",
        "objective.json",
        "comparator.json",
        "recipe/task.py",
        "recipe/providers.py",
        "recipe/contracts.py",
        "recipe/judge_rubric.json",
        "recipe/check.py",
        "recipe/test_recipe.py",
        "recipe/request.json",
        "training-data-contract.json",
        "autodata.pipeline.json",
        "autodata.workspace.json",
        "framework.lock.json",
    }
    if not required_protected.issubset(pipeline.get("protected_paths", [])):
        raise ValueError("pipeline is missing protected paths")
    for key in ("metric", "direction", "minimum_meaningful_delta", "constraints"):
        if pipeline["comparator"][key] != comparator[key]:
            raise ValueError("comparator definitions disagree")
    if objective["metric"] != comparator["metric"] or objective["range"] != [0, 1]:
        raise ValueError("objective differs from comparator")
    expected_constraints = {
        "valid": {"minimum": 0.75},
        "quality": {"minimum": 0.75},
        "neutral_alignment": {"minimum": 0.9},
        "challenge": {"minimum": 0.5},
    }
    if comparator["constraints"] != expected_constraints:
        raise ValueError("protected metric floors changed")
    if (
        set(strategy)
        != {
            "schema",
            "name",
            "system_prompt",
            "global_prompt",
            "family_strategies",
            "challenge_strategy",
            "temperature",
        }
        or strategy["schema"] != "aar.autodata.paired-generation-strategy/v1"
    ):
        raise ValueError("unsupported generation strategy fields")
    if set(strategy["family_strategies"]) != c.FAMILIES:
        raise ValueError("every grounding behavior family requires a strategy")
    for text in [
        strategy["name"],
        strategy["system_prompt"],
        strategy["global_prompt"],
        *strategy["family_strategies"].values(),
    ]:
        if not isinstance(text, str) or not text.strip() or len(text.encode()) > 262144:
            raise ValueError("strategy text must be non-empty and bounded")
    for text in strategy["family_strategies"].values():
        if (
            sum(
                len(value.encode())
                for value in (
                    strategy["system_prompt"],
                    strategy["global_prompt"],
                    text,
                )
            )
            > 720000
        ):
            raise ValueError("combined strategy exceeds the prompt ceiling")
    challenge = strategy["challenge_strategy"]
    if (
        set(challenge) != {"mode", "instruction"}
        or challenge["mode"] != "rewrite_pressure_frame"
        or not isinstance(challenge["instruction"], str)
        or not challenge["instruction"].strip()
        or len(challenge["instruction"].encode()) > 12000
    ):
        raise ValueError("invalid pressure rewrite strategy")
    temperature = strategy["temperature"]
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not 0 <= temperature <= 1.5
    ):
        raise ValueError("temperature must be between 0 and 1.5")
    if (
        set(request.get("primary_axes", [])) != c.PRIMARY_AXES
        or set(read("training-data-contract.json").get("primary_axes", []))
        != c.PRIMARY_AXES
    ):
        raise ValueError("recipe scope must match the grounding")
    c.load_rubric(ROOT / "recipe/judge_rubric.json")

    spec = importlib.util.spec_from_file_location(
        "paired_grounding_builder", ROOT / "grounding/build_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    grounding = read("grounding/manifest.json")
    coverage = builder.load_coverage(ROOT / "grounding/coverage.json")
    rebuilt = builder.build(coverage)
    if grounding != rebuilt:
        raise ValueError(
            "manifest differs from its deterministic coverage/source build"
        )
    if {
        family["id"]: (family["primary_axis"], family["answerability"])
        for family in coverage["behavior_families"]
    } != c.FAMILY_CONTRACTS:
        raise ValueError(
            "protected family/axis/answerability bindings differ from grounding"
        )
    if {axis["id"] for axis in coverage["primary_axes"]} != c.PRIMARY_AXES:
        raise ValueError("declared grounding axes differ from the scorer")
    for source in grounding["sources"]:
        path = (ROOT / source["path"]).resolve()
        if ROOT not in path.parents or not path.is_file():
            raise ValueError("grounding source must be a contained file")
        if (
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            != source["digest"]
        ):
            raise ValueError("grounding source digest mismatch")
    for task in grounding["tasks"]:
        c.validate_task(task)
    if any(
        task_id not in {task["id"] for task in grounding["tasks"]}
        for task_id in grounding["dry_run_task_ids"]
    ):
        raise ValueError("unknown dry-run pair ID")
    result_schema = read("schemas/task-result.schema.json")
    if result_schema["properties"]["generated_items"]["maxItems"] != 1:
        raise ValueError("one accepted pressure row per pair is required")
    metadata = result_schema["properties"]["generated_items"]["items"]["properties"][
        "metadata"
    ]
    if (
        set(metadata["properties"]["primary_axis"]["enum"]) != c.PRIMARY_AXES
        or metadata["properties"]["accepted"] != {"const": True}
        or not {
            "primary_axis",
            "answerability",
            "source_ids",
            "source_provenance",
        }.issubset(metadata["required"])
    ):
        raise ValueError("accepted-row metadata must retain axis and source provenance")
    if read("schemas/generated-pair.schema.json") != c.generation_schema():
        raise ValueError("published generation schema differs from runtime")
    if read("schemas/judge-verdict.schema.json") != c.judge_schema():
        raise ValueError("published judge schema differs from runtime")
    print("Validated paired recipe, source digests, scoring, and mutation boundaries.")


if __name__ == "__main__":
    check()
