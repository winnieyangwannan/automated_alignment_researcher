from __future__ import annotations

from pathlib import Path

import pytest

from aar.slurm_session_recovery import (
    classify_state,
    prepare_intent,
    scheduler_comment_matches,
    transition_intent,
)


def test_unknown_and_running_states_are_not_terminal() -> None:
    assert classify_state("").terminal is False
    assert classify_state("RUNNING").terminal is False
    assert classify_state("PENDING").terminal is False


def test_only_explicit_infrastructure_terminal_states_are_retryable() -> None:
    assert classify_state("NODE_FAIL+").retryable is True
    assert classify_state("TIMEOUT").retryable is True
    assert classify_state("FAILED").retryable is False
    assert classify_state("CANCELLED by 123").retryable is False
    assert classify_state("COMPLETED").successful is True


def test_permanent_application_failure_such_as_http_409_is_not_retried() -> None:
    # The research process exits nonzero for a permanent broker/API rejection;
    # sacct reports FAILED. The controller must not turn missing output into a retry.
    result = classify_state("FAILED")
    assert result.terminal is True
    assert result.category == "permanent"
    assert result.retryable is False


def test_scheduler_comment_reconciliation_deduplicates_squeue_and_sacct() -> None:
    matches = scheduler_comment_matches(
        "aar-run12:attempt:alpha:2",
        [
            "123|aar-run12:attempt:alpha:2\n",
            "123|aar-run12:attempt:alpha:2|RUNNING\n124|other\n",
        ],
    )
    assert matches == ["123"]


def test_controller_restart_reconciles_same_submission_intent(tmp_path: Path) -> None:
    path = tmp_path / "attempt-2.json"
    first = prepare_intent(path, key="alpha:2", comment="aar-run12:alpha:2")
    assert first["status"] == "prepared"
    transition_intent(path, status="submitting")

    restarted = prepare_intent(path, key="alpha:2", comment="aar-run12:alpha:2")
    assert restarted["status"] == "submitting"
    registered = transition_intent(path, status="registered", job_id="987")
    assert registered["job_id"] == "987"
    assert transition_intent(path, status="registered", job_id="987") == registered
    with pytest.raises(RuntimeError, match="another job"):
        transition_intent(path, status="registered", job_id="988")


def test_submission_intent_rejects_identity_drift(tmp_path: Path) -> None:
    path = tmp_path / "intent.json"
    prepare_intent(path, key="alpha:2", comment="aar-run12:alpha:2")
    with pytest.raises(RuntimeError, match="identity changed"):
        prepare_intent(path, key="alpha:3", comment="aar-run12:alpha:3")
