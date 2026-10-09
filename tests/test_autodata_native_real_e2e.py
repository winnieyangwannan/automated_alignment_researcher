from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import patch


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
        environment="oci-runner-firecracker-medium",
        timeout_seconds=3600,
    )
    driver.input = tmp_path / "input"
    driver.input.mkdir()
    driver.executor = lambda: {
        "kind": "test",
        "environment": driver.args.environment,
    }

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
    assert value["executor"]["environment"] == "oci-runner-firecracker-medium"


def test_cli_retries_ambiguous_broker_reachability_failure(tmp_path: Path) -> None:
    driver_type = _load_driver()
    driver = object.__new__(driver_type)
    driver.args = argparse.Namespace(timeout_seconds=3600)
    driver.wrapper = tmp_path / "autodata.py"
    driver.state = tmp_path / "state.db"
    driver.artifacts = tmp_path / "artifacts"
    driver.workspaces = tmp_path / "workspaces"
    driver.root = tmp_path
    driver.environment = {}
    milestones: list[tuple[str, dict[str, object]]] = []
    driver.milestone = lambda name, **fields: milestones.append((name, fields))

    transient = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr="autodata: could not reach AutoData broker\n",
    )
    recovered = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='{"status":"completed"}\n', stderr=""
    )
    with (
        patch("subprocess.run", side_effect=[transient, recovered]) as run,
        patch("time.sleep") as sleep,
    ):
        result = driver.cli("execution", "step", "exe_test")

    assert result == {"status": "completed"}
    assert run.call_count == 2
    sleep.assert_called_once_with(1.0)
    assert milestones == [
        (
            "broker_command_retry",
            {"command": "execution step exe_test", "attempt": 2},
        )
    ]


def test_executor_uses_declared_internal_generator_route() -> None:
    driver_type = _load_driver()
    driver = object.__new__(driver_type)
    driver.args = argparse.Namespace(
        broker_url="http://127.0.0.1:8791",
        environment="oci-runner-firecracker-large",
        generator_url="http://internal-ingress/v1",
        generator_host_header="model.ingress.",
    )

    executor = driver.executor()

    assert executor["non_secret_env"]["AUTODATA_GENERATOR_URL"] == (
        "http://internal-ingress/v1"
    )
    assert executor["non_secret_env"]["AUTODATA_GENERATOR_HOST_HEADER"] == (
        "model.ingress."
    )
