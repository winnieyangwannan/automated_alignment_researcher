"""Fail-fast contracts for lifecycle method-smoke monitoring."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MONITOR_PATH = (
    ROOT
    / "experiments"
    / "dishonest_sycophancy_concealing"
    / "run_10"
    / "canary"
    / "monitor_method_smoke.py"
)
SPEC = importlib.util.spec_from_file_location("monitor_method_smoke", MONITOR_PATH)
assert SPEC is not None and SPEC.loader is not None
monitor_method_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor_method_smoke)


def _attempt(tmp_path: Path) -> tuple[Path, Path]:
    attempt = tmp_path / "attempt"
    metadata = attempt / "metadata"
    team = attempt / "aar_teams" / "team"
    metadata.mkdir(parents=True)
    (team / ".train_submissions").mkdir(parents=True)
    (team / "scores").mkdir()
    (team / "method_smoke").mkdir()
    (metadata / "children.env").write_text(
        "evaluator_jobs=\n"
        "research_chain_jobs=101\n"
        "research_seeds=alpha\n"
    )
    return attempt, team


def test_terminal_chain_without_receipt_fails_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt, _ = _attempt(tmp_path)
    monkeypatch.setattr(monitor_method_smoke, "_job_state", lambda _job: "FAILED")

    with pytest.raises(RuntimeError, match="terminal research chain 'alpha'.*0"):
        monitor_method_smoke.monitor(
            attempt, expected_chains=1, timeout_seconds=60, poll_seconds=0
        )


def test_failed_training_receipt_fails_before_other_receipts_arrive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt, team = _attempt(tmp_path)
    run_id = "gemma4_31b-explore-alpha-1-method-2"
    (team / ".train_submissions" / f"{run_id}.env").write_text(
        f"run_id={run_id}\njob_id=202\n"
    )
    (team / "scores" / f"{run_id}.failed.json").write_text(
        '{"status":"failed","stage":"training"}\n'
    )
    (attempt / "metadata" / "children.env").write_text(
        "evaluator_jobs=\n"
        "research_chain_jobs=101 102\n"
        "research_seeds=alpha beta\n"
    )
    monkeypatch.setattr(monitor_method_smoke, "_job_state", lambda _job: "RUNNING")

    with pytest.raises(RuntimeError, match="method smoke failed"):
        monitor_method_smoke.monitor(
            attempt, expected_chains=2, timeout_seconds=60, poll_seconds=0
        )
