from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (
    ROOT
    / "experiments"
    / "dishonest_sycophancy_concealing"
    / "run_12"
    / "slurm"
    / "chain_controller.sbatch"
)
CHAIN = ROOT / "scripts" / "slurm_aar_chain.sh"


def test_controller_requires_authoritative_terminal_accounting_state() -> None:
    source = CONTROLLER.read_text()

    assert "squeue is advisory only" in source
    assert "sacct_state_unavailable" in source
    assert "aar.slurm_session_recovery classify" in source
    assert 'if [ "${terminal}" = true ]; then' in source
    assert "state=${LAST_JOB_STATE}" in source


def test_controller_retries_only_explicit_infrastructure_failures() -> None:
    source = CONTROLLER.read_text()

    assert 'if [ "${LAST_JOB_RETRYABLE:-false}" != true ]; then' in source
    assert "production_canary_session_failed" in source
    assert "training_smoke_session_failed" in source
    assert "initial_session_produced_no_pair" in source
    assert "session_produced_no_pair" in source
    assert "retrying_same_iteration" not in source


def test_controller_submission_is_idempotent_across_restart() -> None:
    source = CONTROLLER.read_text()

    assert "submission-intents" in source
    assert "--status submitting" in source
    assert '--comment="${comment}"' in source
    assert "reconcile_submission_comment" in source
    assert "ambiguous_submission_intent" in source
    assert "submission_reconciliation_timeout" in source
    assert "controller_restart_reconciled" in source


def test_chain_propagates_service_death_and_bounds_cleanup() -> None:
    source = CHAIN.read_text()

    assert "stop_child_bounded" in source
    assert "ignored TERM; sending KILL" in source
    assert "AutoData broker exited while research was active" in source
    assert "Kimi auth bridge exited while research was active" in source
    assert "AutoData lifecycle supervisor exited while research was active" in source
    assert "aar.research-session-result/v1" in source
