#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path


root = Path(__file__).resolve().parent
strategy = json.loads((root / "generation_strategy.json").read_text())
request = json.loads((root / "request.json").read_text())
coverage = json.loads((root.parent / "grounding" / "coverage.json").read_text())
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
    "system_prompt": 6000,
    "scenario_prompt_prefix": 2000,
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
if coverage.get("schema") != "aar.autodata.grounding-coverage/v1":
    raise SystemExit("grounding coverage schema is invalid")
if (
    not coverage.get("domains")
    or not coverage.get("behavior_patterns")
    or not coverage.get("axes")
):
    raise SystemExit("grounding coverage is incomplete")
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
    markers = ("benchmark", "held-out", "held out", "legal document")
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
