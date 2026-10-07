from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from aar.eval_pod.run_eval import _benchmark_timing_metadata
from aar.phase_timing import (
    phase,
    record_phase,
    require_successful_phases,
    timed_async_phase,
)
from aar.research_loop.tools.server_api_tools import _missing_method_timing_phases


def test_phase_records_success(tmp_path: Path) -> None:
    path = tmp_path / "timings.jsonl"

    with phase("data_generation", path=path, echo=False):
        pass

    event = json.loads(path.read_text())
    assert event["phase"] == "data_generation"
    assert event["status"] == "success"
    assert event["duration_seconds"] >= 0
    assert event["started_at"].endswith("Z")
    assert event["ended_at"].endswith("Z")


def test_phase_records_failure_and_reraises(tmp_path: Path) -> None:
    path = tmp_path / "timings.jsonl"

    with pytest.raises(ValueError, match="broken"):
        with phase("training", path=path, echo=False):
            raise ValueError("broken")

    event = json.loads(path.read_text())
    assert event["status"] == "failure"
    assert event["metadata"]["error_type"] == "ValueError"


def test_required_phases_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "timings.jsonl"
    record_phase("data_generation", 1.0, path=path, echo=False)

    with pytest.raises(RuntimeError, match="training"):
        require_successful_phases(path, ("data_generation", "training"))

    record_phase("training", 2.0, path=path, echo=False)
    require_successful_phases(path, ("data_generation", "training"))


def test_record_phase_rejects_unsafe_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid phase"):
        record_phase("bad phase", 1.0, path=tmp_path / "timings.jsonl", echo=False)


def test_method_timing_phase_static_gate() -> None:
    complete = "\n".join(
        f'with phase("{name}"):\n    pass'
        for name in (
            "data_generation",
            "tokenization",
            "model_loading",
            "training",
            "checkpoint_save",
        )
    )
    assert _missing_method_timing_phases(complete) == []
    assert _missing_method_timing_phases('with phase("training"):\n    pass') == [
        "data_generation",
        "tokenization",
        "model_loading",
        "checkpoint_save",
    ]
    assert "training" in _missing_method_timing_phases('phase("training")')


def test_timed_async_phase_records_success(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "timings.jsonl"
    monkeypatch.setenv("AAR_PHASE_TIMINGS_PATH", str(path))

    @timed_async_phase("research.proposal_review")
    async def operation() -> str:
        return "done"

    assert asyncio.run(operation()) == "done"
    event = json.loads(path.read_text())
    assert event["phase"] == "research.proposal_review"
    assert event["status"] == "success"


def test_held_out_timing_metadata_is_redacted() -> None:
    spec = SimpleNamespace(
        id="secret_benchmark_name",
        category="secret_dimension",
        role="held_out",
    )

    metadata = _benchmark_timing_metadata(spec, worker="0")

    assert metadata == {
        "benchmark": "held_out",
        "category": "held_out",
        "role": "held_out",
        "worker": "0",
    }


def test_run_cli_preserves_failure_exit_code(tmp_path: Path) -> None:
    path = tmp_path / "timings.jsonl"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "aar.phase_timing",
            "run",
            "--path",
            str(path),
            "--phase",
            "eval.adapter_merge",
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ],
        check=False,
    )

    assert completed.returncode == 7
    event = json.loads(path.read_text())
    assert event["phase"] == "eval.adapter_merge"
    assert event["status"] == "failure"
