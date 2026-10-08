from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "autodata_native_real_e2e.py"


def _load_driver():
    spec = importlib.util.spec_from_file_location("autodata_native_real_e2e", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Driver


def test_meta_execution_budget_includes_replenishment_headroom(tmp_path: Path) -> None:
    driver_type = _load_driver()
    driver = object.__new__(driver_type)
    driver.args = argparse.Namespace(
        task_count=8,
        concurrency=8,
        timeout_seconds=3600,
    )
    driver.input = tmp_path / "input"
    driver.input.mkdir()
    driver.executor = lambda: {"kind": "test"}

    pipeline = tmp_path / "pipeline"
    grounding = pipeline / "grounding"
    grounding.mkdir(parents=True)
    (grounding / "manifest.json").write_text("{}\n", encoding="utf-8")

    path = driver._execution_spec(
        pipeline,
        mode="meta_optimize",
        tuning=["t1"],
        validation=["v1"],
    )

    value = json.loads(path.read_text(encoding="utf-8"))
    # The one-iteration native lifecycle requires 29 deterministic attempts
    # for eight tasks; four extra slots permit bounded quality replenishment.
    assert value["budget"]["max_task_attempts"] == 33
    assert value["concurrency"] == 8
