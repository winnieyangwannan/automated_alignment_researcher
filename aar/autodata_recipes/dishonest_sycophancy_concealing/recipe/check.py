#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path


root = Path(__file__).resolve().parent
variant = json.loads((root / "prompt_variant.json").read_text())
request = json.loads((root / "request.json").read_text())
if variant not in ({"variant": "baseline_v1"}, {"variant": "contrastive_v2"}):
    raise SystemExit("prompt variant must be an allowlisted value")
if request.get("schema") != "aar.autodata.recipe-request/v1":
    raise SystemExit("recipe request schema is invalid")
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
        r"\b(?:copy|imitat(?:e|ing)|use|using|reproduc(?:e|ing)|mirror(?:ing)?)\b"
    )
    for clause in clauses:
        if any(marker in clause for marker in markers) and not negative_directives.search(
            clause
        ):
            return True
    return False


if requests_forbidden_source(request["goal"]):
    raise SystemExit("recipe goal requests a forbidden evaluation/source reference")
