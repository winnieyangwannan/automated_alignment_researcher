#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

from task import _load_judge_rubric


root = Path(__file__).resolve().parent
strategy = json.loads((root / "generation_strategy.json").read_text())
request = json.loads((root / "request.json").read_text())
coverage = json.loads((root.parent / "grounding" / "coverage.json").read_text())
pipeline = json.loads((root.parent / "autodata.pipeline.json").read_text())
objective = json.loads((root.parent / "objective.json").read_text())
comparator = json.loads((root.parent / "comparator.json").read_text())
rubric = _load_judge_rubric(root / "judge_rubric.json")
if "recipe/judge_rubric.json" not in pipeline.get("protected_paths", []):
    raise SystemExit("judge rubric must be protected during meta-optimization")
if not rubric["sha256"].startswith("sha256:"):
    raise SystemExit("judge rubric lacks content-addressed identity")
pipeline_comparator = pipeline.get("comparator")
comparator_fields = (
    "metric",
    "direction",
    "minimum_meaningful_delta",
    "constraints",
)
if not isinstance(pipeline_comparator, dict) or any(
    pipeline_comparator.get(key) != comparator.get(key)
    for key in comparator_fields
):
    raise SystemExit("pipeline and standalone comparator definitions disagree")
if (
    pipeline_comparator.get("objective_path") != "objective.json"
    or pipeline_comparator.get("comparator_path") != "comparator.json"
    or objective.get("metric") != comparator.get("metric")
):
    raise SystemExit("objective and comparator references disagree")
if strategy.get("schema") != "aar.autodata.generation-strategy/v1":
    raise SystemExit("generation strategy schema is invalid")
if set(strategy) != {
    "schema",
    "name",
    "system_prompt",
    "scenario_prompt_prefix",
    "temperature",
}:
    raise SystemExit("generation strategy contains missing or unsupported fields")
for key, maximum_bytes in {
    "name": 128,
    # These are authoring inputs to Kimi, not generated training rows. Allow
    # roughly 65,536 English tokens per component (four UTF-8 bytes per token)
    # instead of the former toy 6,000/2,000-byte caps. Exact tokenization and
    # Kimi's 196,608-token request allowance remain enforced by the runtime.
    "system_prompt": 262144,
    "scenario_prompt_prefix": 262144,
}.items():
    if not isinstance(strategy.get(key), str) or not strategy[key].strip():
        raise SystemExit(f"generation strategy requires non-empty {key}")
    if len(strategy[key].encode("utf-8")) > maximum_bytes:
        raise SystemExit(f"generation strategy {key} exceeds {maximum_bytes} bytes")
temperature = strategy.get("temperature")
if (
    isinstance(temperature, bool)
    or not isinstance(temperature, (int, float))
    or not 0 <= float(temperature) <= 1.5
):
    raise SystemExit("generation strategy temperature must be in [0,1.5]")
if request.get("schema") != "aar.autodata.recipe-request/v1":
    raise SystemExit("recipe request schema is invalid")
if coverage.get("schema") != "aar.autodata.grounding-coverage/v2":
    raise SystemExit("grounding coverage schema is invalid")
if (
    not coverage.get("domains")
    or not coverage.get("behavior_patterns")
    or not coverage.get("axes")
):
    raise SystemExit("grounding coverage is incomplete")
expected_axes = {
    "honesty": ("factual_honesty", "dishonesty"),
    "sycophancy_resistance": ("sycophancy_resistance", "sycophancy"),
    "uncertainty_disclosure": (
        "uncertainty_disclosure",
        "concealed_uncertainty",
    ),
}
actual_axes = coverage.get("axes")
if not isinstance(actual_axes, list) or any(
    not isinstance(axis, dict)
    or expected_axes.get(axis.get("id"))
    != (axis.get("teacher_dimension"), axis.get("target_failure_mode"))
    or not isinstance(axis.get("description"), str)
    or not axis["description"].strip()
    for axis in actual_axes
):
    raise SystemExit("grounding axes do not match the protected recipe contract")
if {axis["id"] for axis in actual_axes} != set(expected_axes):
    raise SystemExit("grounding must cover every protected alignment axis")
patterns = coverage.get("behavior_patterns")
if (
    not isinstance(patterns, list)
    or any(
        not isinstance(pattern, dict)
        or pattern.get("primary_axis") not in expected_axes
        for pattern in patterns
    )
    or {pattern["primary_axis"] for pattern in patterns} != set(expected_axes)
):
    raise SystemExit("grounding patterns must cover every primary alignment axis")
limits = {"safety_axis": 128, "training_mechanism": 512, "goal": 2048}
for key, maximum_bytes in limits.items():
    if not isinstance(request.get(key), str) or not request[key].strip():
        raise SystemExit(f"recipe request requires non-empty {key}")
    if len(request[key].encode("utf-8")) > maximum_bytes:
        raise SystemExit(f"recipe request {key} exceeds {maximum_bytes} bytes")


def requests_forbidden_source(text: str) -> bool:
    """Reject source use, while allowing explicit instructions not to use it."""

    lowered = text.lower()
    clauses = re.split(r"[.!?;\n]+", lowered)
    markers = ("benchmark", "held-out", "held out", "evaluator-only")
    negative_directives = re.compile(
        r"\b(?:do not|don't|never|must not|without|avoid)\b[^.!?;]*"
        r"\b(?:copy|imitat(?:e|ing)|use|using|reproduc(?:e|ing)|mirror(?:ing)?|"
        r"mention(?:ing)?|refer(?:ring)?)\b"
    )
    for clause in clauses:
        if any(marker in clause for marker in markers) and not negative_directives.search(
            clause
        ):
            return True
    return False


for label, text in {
    "recipe goal": request["goal"],
    "generation system prompt": strategy["system_prompt"],
    "generation scenario prefix": strategy["scenario_prompt_prefix"],
}.items():
    if requests_forbidden_source(text):
        raise SystemExit(f"{label} requests a forbidden evaluation/source reference")
