from __future__ import annotations

import os
from pathlib import Path

import pytest

from aar.slurm_session_recovery import (
    classify_state,
    prepare_intent,
    reconcile_session_result,
    scheduler_comment_matches,
    transition_intent,
)


def test_unknown_and_running_states_are_not_terminal() -> None:
    assert classify_state("").terminal is False
    assert classify_state("RUNNING").terminal is False
    assert classify_state("PENDING").terminal is False


def test_only_explicit_infrastructure_terminal_states_are_retryable() -> None:
    assert classify_state("NODE_FAIL+").retryable is True
    assert classify_state("BOOT_FAIL").retryable is True
    assert classify_state("PREEMPTED").retryable is True
    assert classify_state("REVOKED").retryable is True
    assert classify_state("TIMEOUT").retryable is False
    assert classify_state("DEADLINE").retryable is False
    assert classify_state("OUT_OF_MEMORY").retryable is False
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


def test_sacct_cancellation_overrides_optimistic_process_completion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research-session-result-1811790.json"
    path.write_text(
        '{"schema":"aar.research-session-result/v1",'
        '"category":"completed","exit_code":0}\n',
        encoding="utf-8",
    )

    result = reconcile_session_result(
        path,
        job_id="1811790",
        slurm_state="CANCELLED",
        slurm_exit_code="0:15",
    )

    assert result["status"] == "failed"
    assert result["category"] == "slurm_cancelled"
    assert result["retryable"] is False
    assert result["exit_code"] == 143
    assert result["terminal_source"] == "sacct"
    assert result["process_result"]["category"] == "completed"


def test_sacct_cancellation_creates_result_when_exit_trap_never_ran(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research-session-result-1811791.json"

    result = reconcile_session_result(
        path,
        job_id="1811791",
        slurm_state="CANCELLED+",
        slurm_exit_code="0:9",
    )

    assert path.is_file()
    assert result["category"] == "slurm_cancelled"
    assert result["exit_code"] == 137
    assert result["process_result"] is None


def test_sacct_reconciliation_is_idempotent_without_nested_markers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research-session-result-1811792.json"
    path.write_text(
        '{"schema":"aar.research-session-result/v1",'
        '"category":"completed","exit_code":0}\n',
        encoding="utf-8",
    )

    first = reconcile_session_result(
        path,
        job_id="1811792",
        slurm_state="CANCELLED",
        slurm_exit_code="0:15",
    )
    second = reconcile_session_result(
        path,
        job_id="1811792",
        slurm_state="CANCELLED",
        slurm_exit_code="0:15",
    )

    assert second["process_result"] == first["process_result"]
    assert second["process_result"]["schema"] == "aar.research-session-result/v1"


def test_atomic_result_write_does_not_follow_predictable_temp_symlink(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research-session-result-1811793.json"
    sensitive = tmp_path / "operator-only"
    sensitive.write_text("unchanged", encoding="utf-8")
    legacy_temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    legacy_temporary.symlink_to(sensitive)

    reconcile_session_result(
        path,
        job_id="1811793",
        slurm_state="FAILED",
        slurm_exit_code="2:0",
    )

    assert sensitive.read_text(encoding="utf-8") == "unchanged"
    assert legacy_temporary.is_symlink()
    assert path.is_file()
