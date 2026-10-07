#!/usr/bin/env python3
from __future__ import annotations

import json
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
for forbidden in ("benchmark", "held-out", "legal document"):
    if forbidden in request["goal"].lower():
        raise SystemExit("recipe goal contains a forbidden evaluation/source reference")
