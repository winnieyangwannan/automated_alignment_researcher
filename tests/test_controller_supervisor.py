from __future__ import annotations

import fcntl
import sys
from pathlib import Path

from aar.controller_supervisor import (
    ChainSnapshot,
    JobStatus,
    decide_recovery,
    main,
)


def _snapshot(
    *,
    training: tuple[str, ...] = (),
    claims: tuple[str, ...] = (),
    pairs: int = 3,
    sessions: int = 7,
) -> ChainSnapshot:
    return ChainSnapshot(
        seed="alpha",
        controller_job="101",
        evaluator_job="102",
        pairs=pairs,
        sessions=sessions,
        active_training_jobs=training,
        unscored_claims=claims,
    )


def _decide(
    snapshot: ChainSnapshot,
    *,
    controller: str = "FAILED",
    evaluator: str = "RUNNING",
    receipt: str | None = "recover",
) -> str:
    return decide_recovery(
        snapshot,
        JobStatus(controller, "1:0"),
        JobStatus(evaluator, "0:0"),
        receipt=receipt,
        target_pairs=50,
        session_ceiling=60,
        restart_count=0,
        max_restarts=8,
    ).action


def test_method_authoring_failure_recovers_from_explicit_receipt() -> None:
    assert _decide(_snapshot()) == "recover"


def test_approved_proposal_interruption_recovers_from_durable_receipt() -> None:
    decision = decide_recovery(
        _snapshot(sessions=8),
        JobStatus("COMPLETED", "0:0"),
        JobStatus("RUNNING", "0:0"),
        receipt="recover",
        target_pairs=50,
        session_ceiling=60,
        restart_count=2,
        max_restarts=8,
    )
    assert decision == type(decision)("recover", "controller_receipt_recover")


def test_active_training_waits_without_submitting_a_controller() -> None:
    assert _decide(_snapshot(training=("301",))) == "wait"


def test_active_evaluation_waits_for_the_healthy_evaluator() -> None:
    assert _decide(_snapshot(claims=("candidate-1",))) == "wait"


def test_terminal_evaluator_allows_unscored_claim_reconciliation() -> None:
    assert (
        _decide(
            _snapshot(claims=("candidate-1",)),
            evaluator="COMPLETED",
        )
        == "recover"
    )


def test_node_preemption_recovers_even_without_process_receipt() -> None:
    assert _decide(_snapshot(), controller="NODE_FAIL", receipt=None) == "recover"


def test_manual_cancellation_without_recovery_receipt_halts() -> None:
    assert _decide(_snapshot(), controller="CANCELLED", receipt=None) == "halt"
    assert _decide(_snapshot(), controller="CANCELLED", receipt="recover") == "halt"


def test_controller_restart_budget_is_bounded() -> None:
    decision = decide_recovery(
        _snapshot(),
        JobStatus("NODE_FAIL", "1:0"),
        JobStatus("RUNNING", "0:0"),
        receipt=None,
        target_pairs=50,
        session_ceiling=60,
        restart_count=8,
        max_restarts=8,
    )
    assert decision.reason == "controller_restart_limit_exhausted"


def test_duplicate_supervisor_lock_fails_closed(
    tmp_path: Path, monkeypatch,
) -> None:
    attempt = tmp_path / "attempt"
    metadata = attempt / "metadata"
    metadata.mkdir(parents=True)
    lock_path = metadata / "controller_supervisor.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "supervise_aar_multiteam.py",
                "--attempt",
                str(attempt),
                "--resume-script",
                str(tmp_path / "resume.sh"),
                "--seeds",
                "alpha",
                "--target-pairs",
                "50",
                "--session-ceiling",
                "60",
                "--max-restarts",
                "8",
                "--max-plan-failures",
                "3",
                "--poll-seconds",
                "60",
                "--backoff-seconds",
                "300",
                "--unknown-state-timeout-seconds",
                "900",
                "--once",
            ],
        )
        assert main() == 2
