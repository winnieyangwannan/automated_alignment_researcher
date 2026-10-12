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
    assert "reconcile-result" in source
    assert "research-session-result-${job_id}.json" in source
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
    assert "stop_active_research" in source
    assert "ignored TERM; sending KILL" in source
    assert "AutoData broker exited while research was active" in source
    assert "Kimi auth bridge exited while research was active" in source
    assert "AutoData lifecycle supervisor exited while research was active" in source
    assert "aar.research-session-result/v1" in source


def test_chain_can_keep_supervisor_alive_after_semantic_turn() -> None:
    source = CHAIN.read_text()

    ownership = source.index("AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE")
    research_wait = source.index('if wait "${_aar_research_pid}"')
    terminal_receipt = source.index("verified terminal lifecycle receipt is ready")
    result_exit = source.index('[ "${_aar_research_result}" -eq 0 ] || exit')
    assert research_wait < ownership < terminal_receipt < result_exit
    assert "training-smoke-canary-complete.json" in source
    assert "production-canary-complete.json" in source
    assert "lifecycle supervisor exited before its terminal receipt" in source


def test_chain_distinguishes_cancellation_from_internal_watchdog_failure() -> None:
    source = CHAIN.read_text()

    assert "terminate_aar_chain TERM 143 cancelled" in source
    assert "terminate_aar_chain USR2 70 runtime_service_failure" in source
    assert 'kill -USR2 "${_aar_chain_pid}"' in source
    assert 'category="${_aar_termination_category}"' in source


def test_chain_retains_signal_marker_before_bounded_child_cleanup() -> None:
    source = CHAIN.read_text()

    marker_write = source.index('"${PY}" - "${TEAM_DIR}/logs/research-session-result-')
    child_stop = source.index("  stop_active_research\n", marker_write)
    broker_stop = source.index("  cleanup_autodata_broker\n", child_stop)
    assert marker_write < child_stop < broker_stop
    assert "os.fsync(handle.fileno())" in source
    assert "os.fsync(directory)" in source
    assert "secrets.token_hex(16)" in source
    assert "dir_fd=directory" in source


def test_chain_terminal_receipt_contains_outer_recovery_state() -> None:
    source = CHAIN.read_text()

    assert '"recovery_disposition": disposition' in source
    assert '"stop_reason": stop_reason' in source
    assert '"completed_pairs": completed_pairs' in source
    assert '"used_sessions": used_sessions' in source
    assert 'disposition = "recover"' in source


def test_chain_keeps_privileged_service_logs_out_of_research_logs() -> None:
    source = CHAIN.read_text()

    assert 'mkdir -p "${TEAM_DIR}/secrets/failure-evidence"' in source
    assert (
        '_aar_auth_bridge_log="${TEAM_DIR}/secrets/failure-evidence/'
        'autodata-kimi-auth-bridge-${SLURM_JOB_ID:-$$}.log"' in source
    )
    assert (
        '_aar_broker_log="${TEAM_DIR}/secrets/failure-evidence/'
        'autodata-broker.log"' in source
    )
    assert (
        '_aar_supervisor_log="${TEAM_DIR}/secrets/failure-evidence/'
        'autodata-lifecycle-supervisor.log"' in source
    )
    assert "_aar_supervisor_log=/dev/null" not in source
    assert '>"${_aar_auth_bridge_log}"' in source
    assert '> "${_aar_broker_log}"' in source
    assert '--log-file "${_aar_supervisor_log}"' in source
    assert '"${TEAM_DIR}/logs/autodata-broker.log"' not in source


def test_chain_exports_proposal_identity_before_supervisor_fork() -> None:
    source = CHAIN.read_text()

    identity = source.index(
        'IDEA_UID="${AAR_IDEA_UID_OVERRIDE:-${MODEL:-qwen}-${SEED}-$(date +%s)}"'
    )
    supervisor = source.index(
        '"${REPO}/scripts/autodata_lifecycle_supervisor.py" run'
    )
    research = source.index('run.py agent --idea-uid "${IDEA_UID}"')
    assert identity < supervisor < research
    assert source.count("IDEA_UID=\"") == 1
    assert ': "${IDEA_UID:?approval coordinator requires IDEA_UID}"' in source
    assert ': "${IDEA_NAME:?approval coordinator requires IDEA_NAME}"' in source
