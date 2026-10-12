from __future__ import annotations

import fcntl
import hashlib
import json
import signal
import shutil
import sqlite3
import stat
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from aar.failure_feedback import FailureFeedbackError
import scripts.autodata_lifecycle_supervisor as lifecycle_supervisor
from scripts.autodata_lifecycle_supervisor import (
    META_STALL_SECONDS,
    META_TIMEOUT_SECONDS,
    PRODUCTION_STALL_SECONDS,
    PRODUCTION_TIMEOUT_SECONDS,
    create_or_reuse_execution,
    execution_creation_key,
    next_subject,
    reconcile_frozen_workspace,
    register_subject,
    restore_database,
    snapshot_database,
)


def test_supervisor_subprocess_failure_keeps_raw_output_operator_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    team = tmp_path / "team"
    team.mkdir()
    monkeypatch.setenv("TEAM_DIR", str(team))
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=9,
        stdout="private generated row",
        stderr="Authorization: Bearer secret-token",
    )

    error = lifecycle_supervisor._subprocess_failure(
        completed,
        error_code="autodata_native_cli_failed",
        stage="autodata_lifecycle",
        public_summary="native AutoData CLI failed",
    )

    assert isinstance(error, FailureFeedbackError)
    public = json.dumps(error.feedback)
    assert "private generated row" not in public
    assert "secret-token" not in public
    assert "evidence" not in error.feedback
    evidence = list((team / "secrets" / "failure-evidence").glob("*.json"))
    assert len(evidence) == 1
    assert stat.S_IMODE(evidence[0].stat().st_mode) == 0o600
    retained = json.loads(evidence[0].read_text())
    assert retained["stdout"] == "private generated row"
    assert "secret-token" in retained["stderr"]


def _frozen_reconcile_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Namespace, str, list[tuple[str, ...]]]:
    state = tmp_path / "state.db"
    retained = tmp_path / "retained.db"
    control = tmp_path / "control.json"
    artifacts = tmp_path / "artifacts"
    workspaces = tmp_path / "workspaces"
    pipeline_root = tmp_path / "pipeline"
    for path in (artifacts, workspaces, pipeline_root / "grounding"):
        path.mkdir(parents=True)
    pipeline = pipeline_root / "autodata.pipeline.json"
    pipeline_manifest = {
        "schema": "autodata.pipeline/v1",
        "checks": [{"argv": ["python3", "recipe/check.py"]}],
    }
    pipeline.write_text(json.dumps(pipeline_manifest), encoding="utf-8")
    ids = [f"task-{index:03d}" for index in range(128)]
    grounding = pipeline_root / "grounding" / "manifest.json"
    grounding.write_text(
        json.dumps(
            {
                "schema": "autodata.grounding/v1",
                "name": "supervisor-test-grounding",
                "description": "Synthetic lifecycle regression grounding.",
                "sources": [],
                "coverage_dimensions": [],
                "dry_run_task_ids": ids[:3],
                "tasks": [{"id": task_id} for task_id in ids],
            }
        ),
        encoding="utf-8",
    )
    digest = "sha256:" + hashlib.sha256(grounding.read_bytes()).hexdigest()
    executor = {
        "kind": "sandoq-firecracker",
        "environment": "env",
        "image": "image",
        "expected_image_id": "image-id",
        "broker_url": "http://127.0.0.1:12345",
        "broker_auth_secret_ref": "AAR_AUTODATA_CAPABILITY",
        "model_backed": True,
        "cpus": 2,
        "memory_mb": 2048,
        "network": "host",
        "workdir": "/workspace",
        "non_secret_env": {"AUTODATA_TARGET_ENABLED": "1"},
    }
    default_spec = {
        "schema": "autodata.execution/v1",
        "mode": "meta_optimize",
        "grounding": {
            "manifest_path": "grounding/manifest.json",
            "digest": digest,
        },
        "executor": executor,
        "budget": {
            "max_iterations": 1,
            "min_iterations": 0,
            "early_stop_patience": None,
            "max_task_attempts": 256,
            "max_wall_seconds": 604800,
        },
        "concurrency": 32,
        "secret_references": ["AAR_AUTODATA_CAPABILITY"],
        # Match the real native freeze output. Trusted orchestration must
        # accept this shape while rebuilding (not trusting) the partition.
        "tuning_task_ids": ["researcher-controlled-tuning"],
        "validation_task_ids": ["researcher-controlled-validation"],
    }
    workspace_id = "ws_" + "1" * 32
    with sqlite3.connect(state) as connection:
        connection.executescript(
            """
            CREATE TABLE actions (scopeKind TEXT, scopeId TEXT, status TEXT);
            CREATE TABLE workspaces (
              id TEXT PRIMARY KEY, status TEXT, phase TEXT, createdAt TEXT,
              maxWallSeconds INTEGER
            );
            CREATE TABLE executions (
              id TEXT PRIMARY KEY, status TEXT, phase TEXT, createdAt TEXT,
              executionJson TEXT, maxWallSeconds INTEGER, workspaceId TEXT,
              pipelineRoot TEXT, workspaceRoot TEXT, snapshotId TEXT,
              pipelineJson TEXT, taskAttemptsUsed INTEGER
            );
            CREATE TABLE study_members (
              studyId TEXT, subjectKind TEXT, subjectId TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO workspaces VALUES (?,?,?,?,?)",
            (workspace_id, "active", "final_pending", "2026-01-01", 604800),
        )
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "exe_default",
                "active",
                "baseline_pending",
                "2026-01-01",
                json.dumps(default_spec),
                604800,
                workspace_id,
                str(pipeline_root),
                None,
                "snapshot-one",
                "{}",
                0,
            ),
        )
        connection.execute(
            "INSERT INTO study_members VALUES (?,?,?)",
            ("study_one", "workspace", workspace_id),
        )
        connection.execute(
            "INSERT INTO study_members VALUES (?,?,?)",
            ("study_one", "execution", "exe_default"),
        )
    register_subject(state, control, kind="workspace", subject_id=workspace_id)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "UPDATE workspaces SET status='frozen',phase='frozen' WHERE id=?",
            (workspace_id,),
        )
    settings = {
        "meta": {
            "maximum_iterations": 3,
            "minimum_iterations": 3,
            "early_stop_patience": 3,
            "tuning_tasks": 64,
            "validation_tasks": 32,
            "test_tasks": 32,
        },
        "production": {
            "initial_tasks": 1250,
            "required_rows": 1000,
            "minimum_successful_task_fraction": 0.95,
        },
        "concurrency": 32,
        "campaign_policy": {
            "environment": "env",
            "image": "image",
            "expected_image_id": "image-id",
            "max_cpus": 2,
            "max_memory_mb": 2048,
            "required_solve_env": {"AUTODATA_TARGET_ENABLED": "1"},
        },
        "broker_url": "http://127.0.0.1:12345",
        "meta_wall_seconds": 604800,
        "production_wall_seconds": 604800,
        "meta_evaluation_attempts": 608,
        "meta_finalization_retry_attempts": 96,
        "meta_model_task_attempts": 704,
        "meta_task_attempts": 707,
        "pipeline_checks_per_iteration": 1,
        "trusted_pipeline_manifest": pipeline_manifest,
        "production_task_attempts": 2500,
    }
    monkeypatch.setattr(
        lifecycle_supervisor, "_trusted_execution_settings", lambda **_: settings
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "validate_generation_inputs",
        lambda **_: {"schema": "aar.autodata.training-data-contract/v1"},
    )
    calls: list[tuple[str, ...]] = []

    def native(*arguments: object) -> dict[str, object]:
        command = tuple(str(value) for value in arguments[4:])
        calls.append(command)
        if command[:2] == ("execution", "create"):
            manifest_path = Path(command[command.index("--execution") + 1])
            spec = manifest_path.read_text(encoding="utf-8")
            with sqlite3.connect(state) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM executions WHERE id='exe_canonical'"
                ).fetchone()
                if exists is None:
                    connection.execute(
                        "INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            "exe_canonical",
                            "active",
                            "baseline_pending",
                            "2026-01-02",
                            spec,
                            604800,
                            workspace_id,
                            str(pipeline_root),
                            None,
                            "snapshot-one",
                            "{}",
                            0,
                        ),
                    )
                    connection.execute(
                        "INSERT INTO study_members VALUES (?,?,?)",
                        ("study_one", "execution", "exe_canonical"),
                    )
            return {"execution_id": "exe_canonical", "status": "active"}
        assert command == ("cancel", "exe_default")
        with sqlite3.connect(state) as connection:
            connection.execute(
                "UPDATE executions SET status='cancelled',phase='cancelled' "
                "WHERE id='exe_default'"
            )
        return {"execution_id": "exe_default", "status": "cancelled"}

    monkeypatch.setattr(lifecycle_supervisor, "_native_cli", native)
    args = Namespace(
        python=Path(sys.executable),
        state=state,
        retained_state=retained,
        control_file=control,
        artifacts=artifacts,
        workspaces=workspaces,
        campaign_policy=tmp_path / "policy.json",
        training_data_contract=tmp_path / "contract.json",
        resolved_config=None,
        resolved_config_sha256=None,
        campaign_policy_sha256=None,
    )
    return args, workspace_id, calls


def test_control_lock_wait_is_bounded_and_fails_loudly(tmp_path: Path) -> None:
    control = tmp_path / "control.json"
    lock_path = tmp_path / "control.json.lock"
    with lock_path.open("a+", encoding="utf-8") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="timed out acquiring"):
            lifecycle_supervisor._with_control_lock(control, timeout_seconds=0.01)


def test_snapshot_backup_has_a_hard_deadline(tmp_path: Path) -> None:
    source = tmp_path / "live.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE events(value TEXT)")
        connection.execute("INSERT INTO events VALUES ('ready')")

    with pytest.raises(TimeoutError, match="exceeded its deadline"):
        snapshot_database(
            source,
            tmp_path / "retained.db",
            reason="deadline-test",
            timeout_seconds=1e-9,
        )


def test_supervisor_cleanup_escalates_term_to_kill_with_bounded_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        pid = 4321
        returncode = None

        def __init__(self) -> None:
            self.waits: list[int] = []

        def poll(self) -> None:
            return None

        def wait(self, *, timeout: int) -> int:
            self.waits.append(timeout)
            if len(self.waits) == 1:
                raise subprocess.TimeoutExpired("native", timeout)
            self.returncode = -signal.SIGKILL
            return self.returncode

    signals: list[int] = []
    monkeypatch.setattr(
        lifecycle_supervisor.os,
        "killpg",
        lambda _pid, signum: signals.append(signum),
    )
    supervisor = lifecycle_supervisor.Supervisor(Namespace())
    process = Process()
    supervisor.current = process  # type: ignore[assignment]

    assert supervisor._terminate_current_process_group() == -signal.SIGKILL
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert process.waits == [
        lifecycle_supervisor.PROCESS_TERMINATE_GRACE_SECONDS,
        lifecycle_supervisor.PROCESS_KILL_GRACE_SECONDS,
    ]


def _state(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE actions (
              scopeKind TEXT, scopeId TEXT, status TEXT
            );
            CREATE TABLE workspaces (
              id TEXT, status TEXT, phase TEXT, createdAt TEXT,
              maxWallSeconds INTEGER
            );
            CREATE TABLE executions (
              id TEXT, status TEXT, phase TEXT, createdAt TEXT,
              executionJson TEXT, maxWallSeconds INTEGER
            );
            CREATE TABLE marker (value TEXT);
            """
        )
        connection.execute("INSERT INTO marker VALUES ('durable')")


def test_snapshot_is_integrity_bound_and_restorable(tmp_path: Path) -> None:
    live = tmp_path / "node" / "state.db"
    retained = tmp_path / "retained" / "state.db"
    live.parent.mkdir()
    _state(live)

    assert snapshot_database(live, retained, reason="test-milestone") is True
    metadata = json.loads(
        retained.with_name("state.db.snapshot.json").read_text(encoding="utf-8")
    )
    assert metadata["reason"] == "test-milestone"
    assert metadata["sha256"] == hashlib.sha256(retained.read_bytes()).hexdigest()

    restored = tmp_path / "new-node" / "state.db"
    assert restore_database(retained, restored) is True
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("durable",)


def test_frozen_workspace_automatically_creates_registers_and_cleans_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, workspace_id, calls = _frozen_reconcile_fixture(tmp_path, monkeypatch)

    result = reconcile_frozen_workspace(args, workspace_id)

    assert result["execution_id"] == "exe_canonical"
    with sqlite3.connect(args.state) as connection:
        default_status = connection.execute(
            "SELECT status FROM executions WHERE id='exe_default'"
        ).fetchone()[0]
        canonical_spec = json.loads(
            connection.execute(
                "SELECT executionJson FROM executions WHERE id='exe_canonical'"
            ).fetchone()[0]
        )
    assert default_status == "cancelled"
    assert canonical_spec["budget"]["max_iterations"] == 3
    assert canonical_spec["budget"]["min_iterations"] == 3
    assert canonical_spec["budget"]["early_stop_patience"] == 3
    assert canonical_spec["budget"]["max_task_attempts"] == 707
    assert isinstance(canonical_spec["split_seed"], int)
    assert len(canonical_spec["tuning_task_ids"]) == 64
    assert len(canonical_spec["validation_task_ids"]) == 32
    canonical_pipeline = Path(
        next(
            call[call.index("--pipeline") + 1]
            for call in calls
            if call[:2] == ("execution", "create")
        )
    ).parent
    meta_manifest = json.loads(
        (canonical_pipeline / canonical_spec["grounding"]["manifest_path"]).read_text()
    )
    test_manifest = json.loads(
        (
            canonical_pipeline
            / canonical_spec["test_grounding"]["manifest_path"]
        ).read_text()
    )
    meta_ids = [task["id"] for task in meta_manifest["tasks"]]
    assert canonical_spec["tuning_task_ids"] == meta_ids[:64]
    assert canonical_spec["validation_task_ids"] == meta_ids[64:96]
    assert "researcher-controlled-tuning" not in canonical_spec["tuning_task_ids"]
    assert len(meta_manifest["tasks"]) == 96
    assert len(test_manifest["tasks"]) == 32
    test_ids = [task["id"] for task in test_manifest["tasks"]]
    assert meta_manifest["dry_run_task_ids"] == meta_ids[:3]
    assert test_manifest["dry_run_task_ids"] == test_ids[:3]
    assert {task["id"] for task in meta_manifest["tasks"]}.isdisjoint(
        task["id"] for task in test_manifest["tasks"]
    )
    subjects = json.loads(args.control_file.read_text(encoding="utf-8"))["subjects"]
    assert subjects[0]["status"] == "completed"
    assert subjects[1]["subject_id"] == "exe_canonical"
    assert subjects[1]["status"] == "registered"
    assert calls[-1] == ("cancel", "exe_default")


def test_frozen_workspace_rejects_model_added_pipeline_check_before_native_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, workspace_id, calls = _frozen_reconcile_fixture(tmp_path, monkeypatch)
    with sqlite3.connect(args.state) as connection:
        root = Path(
            connection.execute(
                "SELECT pipelineRoot FROM executions WHERE id='exe_default'"
            ).fetchone()[0]
        )
    pipeline = root / "autodata.pipeline.json"
    value = json.loads(pipeline.read_text())
    value["checks"].append({"argv": ["python3", "recipe/untrusted.py"]})
    pipeline.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(FailureFeedbackError) as failure:
        reconcile_frozen_workspace(args, workspace_id)
    assert (
        failure.value.feedback["error_code"]
        == "workspace_canonical_pipeline_invalid"
    )
    assert calls == []


def test_semantic_operator_identity_ignores_only_restart_local_transport() -> None:
    first = {
        "broker_url": "http://127.0.0.1:1111",
        "campaign_policy": {
            "max_cost_usd": "5500",
            "required_solve_env": {
                "AUTODATA_GENERATOR_URL": "http://127.0.0.1:2222/v1",
                "AUTODATA_GENERATOR_HOST_HEADER": "one.internal",
                "AUTODATA_TARGET_ENABLED": "1",
            },
        },
        "concurrency": 32,
    }
    restarted = json.loads(json.dumps(first))
    restarted["broker_url"] = "http://127.0.0.1:3333"
    restarted["campaign_policy"]["required_solve_env"].update(
        AUTODATA_GENERATOR_URL="http://127.0.0.1:4444/v1",
        AUTODATA_GENERATOR_HOST_HEADER="two.internal",
    )
    assert lifecycle_supervisor._semantic_operator_settings(
        first
    ) == lifecycle_supervisor._semantic_operator_settings(restarted)

    restarted["concurrency"] = 16
    assert lifecycle_supervisor._semantic_operator_settings(
        first
    ) != lifecycle_supervisor._semantic_operator_settings(restarted)


def test_frozen_workspace_reports_safe_canonical_manifest_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, workspace_id, calls = _frozen_reconcile_fixture(tmp_path, monkeypatch)
    with sqlite3.connect(args.state) as connection:
        raw = connection.execute(
            "SELECT executionJson FROM executions WHERE id='exe_default'"
        ).fetchone()[0]
        spec = json.loads(raw)
        spec["unexpected_researcher_field"] = "private value"
        connection.execute(
            "UPDATE executions SET executionJson=? WHERE id='exe_default'",
            (json.dumps(spec),),
        )

    with pytest.raises(FailureFeedbackError) as captured:
        reconcile_frozen_workspace(args, workspace_id)

    assert calls == []
    assert captured.value.feedback["error_code"] == (
        "workspace_canonical_manifest_invalid"
    )
    assert captured.value.feedback["summary"] == (
        "canonical workspace execution manifest is invalid"
    )
    assert "private value" not in json.dumps(captured.value.feedback)


def test_frozen_workspace_recovers_create_before_register_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, workspace_id, calls = _frozen_reconcile_fixture(tmp_path, monkeypatch)
    real_snapshot = lifecycle_supervisor.snapshot_database
    snapshots = 0

    def interrupt_first_snapshot(*arguments: object, **keywords: object) -> bool:
        nonlocal snapshots
        snapshots += 1
        if snapshots == 1:
            return False
        return real_snapshot(*arguments, **keywords)

    monkeypatch.setattr(
        lifecycle_supervisor, "snapshot_database", interrupt_first_snapshot
    )
    with pytest.raises(RuntimeError, match="retain canonical"):
        reconcile_frozen_workspace(args, workspace_id)

    result = reconcile_frozen_workspace(args, workspace_id)

    assert result["execution_id"] == "exe_canonical"
    assert sum(call[:2] == ("execution", "create") for call in calls) == 2
    with sqlite3.connect(args.state) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM executions WHERE id='exe_canonical'"
        ).fetchone()[0] == 1


def test_frozen_workspace_reconciliation_is_repeat_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, workspace_id, calls = _frozen_reconcile_fixture(tmp_path, monkeypatch)
    first = reconcile_frozen_workspace(args, workspace_id)
    second = reconcile_frozen_workspace(args, workspace_id)

    assert first["execution_id"] == second["execution_id"]
    assert sum(call == ("cancel", "exe_default") for call in calls) == 1


def test_frozen_workspace_preserves_progressed_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, workspace_id, calls = _frozen_reconcile_fixture(tmp_path, monkeypatch)
    with sqlite3.connect(args.state) as connection:
        connection.execute(
            "UPDATE executions SET phase='awaiting_mutation',taskAttemptsUsed=1 "
            "WHERE id='exe_default'"
        )

    with pytest.raises(RuntimeError, match="progressed"):
        reconcile_frozen_workspace(args, workspace_id)
    assert calls == []
    with sqlite3.connect(args.state) as connection:
        assert connection.execute(
            "SELECT status FROM executions WHERE id='exe_default'"
        ).fetchone()[0] == "active"


def test_frozen_workspace_registration_sla_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, workspace_id, calls = _frozen_reconcile_fixture(tmp_path, monkeypatch)
    lifecycle_supervisor._update_registration(
        args.control_file,
        kind="workspace",
        subject_id=workspace_id,
        reconcile_started_at=lifecycle_supervisor._utc_now(),
        reconcile_attempts=3,
    )

    with pytest.raises(RuntimeError, match="three reconciliation attempts"):
        reconcile_frozen_workspace(args, workspace_id)
    assert calls == []


def test_supervisor_stops_three_unchanged_nonzero_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = lifecycle_supervisor.Supervisor(
        Namespace(state=tmp_path / "state.db")
    )
    monkeypatch.setattr(supervisor, "_progress_signature", lambda: (("", 1, 2),))
    subject = lifecycle_supervisor.Subject(
        "execution", "exe_stuck", "final_pending", 60, 60
    )

    supervisor._record_step_outcome(
        subject, return_code=2, timed_out=False, stalled=False
    )
    supervisor._record_step_outcome(
        subject, return_code=2, timed_out=False, stalled=False
    )
    with pytest.raises(RuntimeError, match="three times without state progress"):
        supervisor._record_step_outcome(
            subject, return_code=2, timed_out=False, stalled=False
        )


def test_supervisor_surfaces_allowlisted_native_contract_diagnostic(
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "supervisor.log"
    with log_file.open("a", encoding="utf-8", buffering=1) as log_handle:
        supervisor = lifecycle_supervisor.Supervisor(
            Namespace(
                state=tmp_path / "state.db",
                log_file=log_file,
                log_handle=log_handle,
            )
        )
        offset = log_handle.tell()
        log_handle.write(
            "autodata: analysis action result must include a non-empty proposal\n"
        )
        diagnostic = supervisor._safe_step_diagnostic(offset)

    assert diagnostic == "analysis action result must include a non-empty proposal"
    subject = lifecycle_supervisor.Subject(
        "execution", "exe_stuck", "awaiting_analysis", 60, 60
    )
    supervisor._record_step_outcome(
        subject,
        return_code=2,
        timed_out=False,
        stalled=False,
        safe_diagnostic=diagnostic,
    )
    supervisor._record_step_outcome(
        subject,
        return_code=2,
        timed_out=False,
        stalled=False,
        safe_diagnostic=diagnostic,
    )
    with pytest.raises(
        lifecycle_supervisor.NativeStepFailure,
        match="analysis action result must include a non-empty proposal",
    ) as failure:
        supervisor._record_step_outcome(
            subject,
            return_code=2,
            timed_out=False,
            stalled=False,
            safe_diagnostic=diagnostic,
        )
    assert failure.value.error_code == "native_action_result_contract_failed"


@pytest.mark.parametrize(
    ("diagnostic", "error_code"),
    [
        (
            "task_attempts budget exceeded",
            "native_task_attempt_budget_exceeded",
        ),
        (
            "task_attempts budget insufficient for atomic batch: "
            "requires 93, remaining 88",
            "native_task_attempt_budget_insufficient",
        ),
        (
            "iterations budget insufficient for atomic batch: "
            "requires 1, remaining 0",
            "native_iteration_budget_insufficient",
        ),
        ("iterations budget exceeded", "native_iteration_budget_exceeded"),
        ("wall-clock budget exceeded", "native_wall_clock_budget_exceeded"),
        (
            "workspace task-attempt budget exceeded",
            "native_workspace_task_attempt_budget_exceeded",
        ),
        (
            "workspace revision budget exceeded",
            "native_workspace_revision_budget_exceeded",
        ),
    ],
)
def test_supervisor_fails_immediately_on_permanent_native_budget_diagnostic(
    tmp_path: Path,
    diagnostic: str,
    error_code: str,
) -> None:
    log_file = tmp_path / "supervisor.log"
    with log_file.open("a", encoding="utf-8", buffering=1) as log_handle:
        supervisor = lifecycle_supervisor.Supervisor(
            Namespace(
                state=tmp_path / "state.db",
                log_file=log_file,
                log_handle=log_handle,
            )
        )
        offset = log_handle.tell()
        log_handle.write(f"autodata: {diagnostic}\n")
        safe_diagnostic = supervisor._safe_step_diagnostic(offset)

    assert safe_diagnostic == diagnostic
    subject = lifecycle_supervisor.Subject(
        "execution", "exe_budget", "final_pending", 60, 60
    )
    with pytest.raises(
        lifecycle_supervisor.NativeStepFailure,
        match="failed permanently",
    ) as failure:
        supervisor._record_step_outcome(
            subject,
            return_code=2,
            timed_out=False,
            stalled=False,
            safe_diagnostic=safe_diagnostic,
        )
    assert failure.value.error_code == error_code
    assert failure.value.public_summary.endswith(diagnostic)
    assert supervisor.failed_step_count == 0


def test_status_heartbeat_refreshes_unchanged_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = lifecycle_supervisor.Supervisor(
        Namespace(status_file=tmp_path / "status.json")
    )
    writes: list[dict[str, object]] = []
    ticks = iter(
        [
            0.0,
            lifecycle_supervisor.DEFAULT_STATUS_HEARTBEAT_SECONDS - 1,
            lifecycle_supervisor.DEFAULT_STATUS_HEARTBEAT_SECONDS + 1,
        ]
    )
    monkeypatch.setattr(lifecycle_supervisor.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_atomic_json",
        lambda _path, value: writes.append(value),
    )

    supervisor._write_status(state="stepping", phase="final_pending")
    supervisor._write_status(state="stepping", phase="final_pending")
    supervisor._write_status(state="stepping", phase="final_pending")

    assert len(writes) == 2
    assert all(value["state"] == "stepping" for value in writes)


def test_long_native_step_refreshes_supervisor_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Process:
        returncode = 0

        def __init__(self) -> None:
            self.polls = 0

        def poll(self) -> int | None:
            self.polls += 1
            return None if self.polls <= 3 else 0

    log_file = tmp_path / "supervisor.log"
    with log_file.open("a", encoding="utf-8", buffering=1) as log_handle:
        args = Namespace(
            python=Path(sys.executable),
            state=tmp_path / "state.db",
            artifacts=tmp_path / "artifacts",
            workspaces=tmp_path / "workspaces",
            log_file=log_file,
            log_handle=log_handle,
            snapshot_interval_seconds=3600,
            poll_seconds=0,
            error_backoff_seconds=0,
        )
        supervisor = lifecycle_supervisor.Supervisor(args)
        writes: list[dict[str, object]] = []
        monkeypatch.setattr(supervisor, "_write_status", lambda **value: writes.append(value))
        monkeypatch.setattr(supervisor, "_progress_signature", lambda _subject: ())
        monkeypatch.setattr(supervisor, "_snapshot", lambda _reason: None)
        monkeypatch.setattr(lifecycle_supervisor.time, "sleep", lambda _seconds: None)
        monkeypatch.setattr(
            lifecycle_supervisor.subprocess,
            "Popen",
            lambda *args, **kwargs: Process(),
        )

        supervisor._step(
            lifecycle_supervisor.Subject(
                "execution", "exe_long", "final_pending", None, 1200
            )
        )

    stepping = [value for value in writes if value.get("state") == "stepping"]
    assert len(stepping) >= 2
    assert all(value.get("phase") == "final_pending" for value in stepping)


def test_synchronous_host_work_refreshes_supervisor_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = lifecycle_supervisor.Supervisor(
        Namespace(status_file=tmp_path / "status.json")
    )
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(lifecycle_supervisor, "DEFAULT_STATUS_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_atomic_json",
        lambda _path, value: writes.append(value),
    )

    result = supervisor._call_with_status_heartbeat(
        lambda: lifecycle_supervisor.time.sleep(0.04),
        state="reconciling",
        subject_kind="execution",
        subject_id="exe_long_transition",
    )

    assert result is None
    reconciling = [value for value in writes if value["state"] == "reconciling"]
    assert len(reconciling) >= 3
    assert all(
        value.get("subject_id") == "exe_long_transition" for value in reconciling
    )


def test_long_idle_sleep_refreshes_supervisor_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = lifecycle_supervisor.Supervisor(
        Namespace(status_file=tmp_path / "status.json")
    )
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(lifecycle_supervisor, "DEFAULT_STATUS_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_atomic_json",
        lambda _path, value: writes.append(value),
    )

    supervisor._sleep_with_status_heartbeat(0.04, state="idle")

    idle = [value for value in writes if value["state"] == "idle"]
    assert len(idle) >= 3


def test_signal_handler_does_not_reenter_atomic_status_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = lifecycle_supervisor.Supervisor(
        Namespace(status_file=tmp_path / "status.json")
    )
    writes: list[dict[str, object]] = []

    def atomic_write(_path: Path, value: dict[str, object]) -> None:
        if not writes:
            supervisor._signal(signal.SIGTERM, None)
        writes.append(value)

    monkeypatch.setattr(lifecycle_supervisor, "_atomic_json", atomic_write)

    supervisor._write_status(state="running")

    assert supervisor.stop_requested is True
    assert supervisor.stop_signal == signal.SIGTERM
    assert [value["state"] for value in writes] == ["running"]


def test_run_serially_publishes_signal_stop_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = lifecycle_supervisor.Supervisor(
        Namespace(
            status_file=tmp_path / "status.json",
            lock_file=tmp_path / "supervisor.lock",
            state=tmp_path / "state.db",
            retained_state=tmp_path / "retained.db",
        )
    )
    writes: list[dict[str, object]] = []
    supervisor.stop_requested = True
    supervisor.stop_signal = signal.SIGTERM
    monkeypatch.setattr(supervisor, "_lock", lambda: None)
    monkeypatch.setattr(
        lifecycle_supervisor,
        "snapshot_database",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(lifecycle_supervisor.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_atomic_json",
        lambda _path, value: writes.append(value),
    )

    assert supervisor.run() == 0
    assert [value["state"] for value in writes] == [
        "starting",
        "stopping",
        "stopped",
    ]
    assert writes[-1]["signal"] == signal.SIGTERM


@pytest.mark.parametrize(
    ("workspace_id", "transition", "expected_kind", "expected_id"),
    [
        ("ws_long", None, "workspace", "ws_long"),
        (None, ("exe_long", "meta_optimize"), "execution", "exe_long"),
    ],
)
def test_run_wraps_every_reconciliation_edge_with_heartbeat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workspace_id: str | None,
    transition: tuple[str, str] | None,
    expected_kind: str,
    expected_id: str,
) -> None:
    args = Namespace(
        state=tmp_path / "state.db",
        retained_state=tmp_path / "retained.db",
        control_file=tmp_path / "control.json",
        status_file=tmp_path / "status.json",
        lock_file=tmp_path / "supervisor.lock",
        error_backoff_seconds=0,
        poll_seconds=0.01,
        production_timeout_seconds=60,
        stage_timeout_policy="enforce",
    )
    supervisor = lifecycle_supervisor.Supervisor(args)
    calls: list[dict[str, object]] = []

    def wrapped(operation, **status_fields):
        calls.append(status_fields)
        return operation()

    def finish_reconciliation(*_args):
        supervisor.stop_requested = True
        return {"transition": "complete"}

    monkeypatch.setattr(supervisor, "_lock", lambda: None)
    monkeypatch.setattr(
        supervisor,
        "_snapshot",
        lambda _reason, **_kwargs: None,
    )
    monkeypatch.setattr(supervisor, "_write_status", lambda **_fields: None)
    monkeypatch.setattr(supervisor, "_call_with_status_heartbeat", wrapped)
    monkeypatch.setattr(lifecycle_supervisor.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_frozen_registered_workspace",
        lambda *_args: workspace_id,
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_pending_completed_execution_transition",
        lambda *_args: transition,
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "reconcile_frozen_workspace",
        finish_reconciliation,
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "reconcile_completed_execution_transition",
        finish_reconciliation,
    )

    assert supervisor.run() == 0
    assert any(
        call.get("state") == "reconciling"
        and call.get("subject_kind") == expected_kind
        and call.get("subject_id") == expected_id
        for call in calls
    )


def test_supervisor_stops_repeated_failure_despite_database_mtime_progress(
    tmp_path: Path,
) -> None:
    supervisor = lifecycle_supervisor.Supervisor(
        Namespace(state=tmp_path / "state.db")
    )
    supervisor.args.state.write_bytes(b"first")
    subject = lifecycle_supervisor.Subject(
        "execution", "exe_progressing", "final_pending", 60, 60
    )

    supervisor._record_step_outcome(
        subject, return_code=2, timed_out=False, stalled=False
    )
    supervisor.args.state.write_bytes(b"second and larger")
    supervisor._record_step_outcome(
        subject, return_code=2, timed_out=False, stalled=False
    )
    supervisor.args.state.write_bytes(b"third and larger still")
    with pytest.raises(RuntimeError, match="three times without state progress"):
        supervisor._record_step_outcome(
            subject, return_code=2, timed_out=False, stalled=False
        )


def test_supervisor_resets_nonzero_counter_on_phase_transition(tmp_path: Path) -> None:
    supervisor = lifecycle_supervisor.Supervisor(
        Namespace(state=tmp_path / "state.db")
    )
    first = lifecycle_supervisor.Subject(
        "execution", "exe_progressing", "baseline_pending", 60, 60
    )
    second = lifecycle_supervisor.Subject(
        "execution", "exe_progressing", "awaiting_mutation", 60, 60
    )
    supervisor._record_step_outcome(
        first, return_code=2, timed_out=False, stalled=False
    )
    supervisor._record_step_outcome(
        first, return_code=2, timed_out=False, stalled=False
    )
    supervisor._record_step_outcome(
        second, return_code=2, timed_out=False, stalled=False
    )
    assert supervisor.failed_step_count == 1


def test_semantic_progress_ignores_database_churn_but_tracks_phase(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.db"
    _state(state)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_semantic",
                "active",
                "baseline_pending",
                "2026-01-01",
                json.dumps({"mode": "meta_optimize"}),
                6300,
            ),
        )
    supervisor = lifecycle_supervisor.Supervisor(Namespace(state=state))
    subject = lifecycle_supervisor.Subject(
        "execution", "exe_semantic", "baseline_pending", 60, 60
    )
    before = supervisor._progress_signature(subject)
    with sqlite3.connect(state) as connection:
        connection.execute("INSERT INTO marker VALUES ('unrelated WAL churn')")
    assert supervisor._progress_signature(subject) == before
    with sqlite3.connect(state) as connection:
        connection.execute(
            "UPDATE executions SET phase='awaiting_mutation' WHERE id='exe_semantic'"
        )
    assert supervisor._progress_signature(subject) != before


def test_default_cancellation_rejects_counter_attempt_row_mismatch(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.db"
    with sqlite3.connect(state) as connection:
        connection.executescript(
            """
            CREATE TABLE task_attempts (
              id TEXT, scopeKind TEXT, scopeId TEXT, state TEXT
            );
            CREATE TABLE events (
              scopeKind TEXT, scopeId TEXT, kind TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO task_attempts VALUES (?,?,?,?)",
            ("attempt_one", "execution", "exe_default", "succeeded"),
        )
    with pytest.raises(RuntimeError, match="counter and persisted attempt rows"):
        lifecycle_supervisor._execution_attempts(
            state,
            {"id": "exe_default", "taskAttemptsUsed": 0},
        )


def test_production_pipeline_materialization_is_disjoint_and_idempotent(
    tmp_path: Path,
) -> None:
    recipe = (
        Path(__file__).resolve().parents[1]
        / "aar"
        / "autodata_recipes"
        / "dishonest_sycophancy_concealing"
    )
    winner = tmp_path / "winner"
    (winner / "grounding").mkdir(parents=True)
    shutil.copy2(
        recipe / "grounding" / "build_manifest.py",
        winner / "grounding" / "build_manifest.py",
    )
    shutil.copy2(
        recipe / "grounding" / "coverage.json",
        winner / "grounding" / "coverage.json",
    )
    (winner / "autodata.pipeline.json").write_text("{}", encoding="utf-8")
    destination = tmp_path / "production"
    reserved = [f"safety-sft-{index:04d}" for index in range(1, 129)]

    first_pipeline, first_ref = (
        lifecycle_supervisor._copy_tree_with_production_grounding(
            python=Path(sys.executable),
            winner=winner,
            destination=destination,
            task_count=1250,
            seed=20262008,
            reserved_task_ids=reserved,
        )
    )
    second_pipeline, second_ref = (
        lifecycle_supervisor._copy_tree_with_production_grounding(
            python=Path(sys.executable),
            winner=winner,
            destination=destination,
            task_count=1250,
            seed=20262008,
            reserved_task_ids=reserved,
        )
    )

    manifest = json.loads(
        (destination / "grounding" / "production-manifest.json").read_text()
    )
    production_ids = {task["id"] for task in manifest["tasks"]}
    assert first_pipeline == second_pipeline
    assert first_ref == second_ref
    assert len(production_ids) == 1250
    assert production_ids.isdisjoint(reserved)
    assert manifest["tasks"][0]["id"] == "safety-prod-0001"


def test_completed_meta_transition_recovers_without_duplicate_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = tmp_path / "team" / "autodata" / "run-one"
    artifacts = tmp_path / "artifacts"
    workspaces = tmp_path / "workspaces"
    retained = tmp_path / "retained.db"
    control = tmp_path / "control.json"
    for path in (run_root, artifacts, workspaces):
        path.mkdir(parents=True)
    workspace_id = "ws_" + "1" * 32
    meta_id = "exe_" + "2" * 32
    production_id = "exe_" + "3" * 32
    lifecycle_supervisor._atomic_json(
        control,
        {
            "schema": lifecycle_supervisor.CONTROL_SCHEMA,
            "subjects": [
                {
                    "kind": "workspace",
                    "subject_id": workspace_id,
                    "status": "completed",
                    "canonical_execution_id": meta_id,
                },
                {
                    "kind": "execution",
                    "subject_id": meta_id,
                    "status": "registered",
                },
            ],
        },
    )
    settings = {
        "meta": {
            "maximum_iterations": 3,
            "minimum_iterations": 3,
            "early_stop_patience": 3,
            "tuning_tasks": 64,
            "validation_tasks": 32,
            "test_tasks": 32,
        },
        "production": {
            "initial_tasks": 1250,
            "required_rows": 1000,
            "minimum_successful_task_fraction": 0.95,
        },
        "concurrency": 32,
        "campaign_policy": {},
        "broker_url": "http://127.0.0.1:1",
    }
    bootstrap = {
        "run_id": "run-one",
        "idea_name": "method_one",
        "code_hash": "a" * 64,
        "workspace_id": workspace_id,
        "study_id": "study-one",
    }
    production_root = run_root / "production"
    (production_root / "grounding").mkdir(parents=True)
    pipeline = production_root / "autodata.pipeline.json"
    pipeline.write_text("{}", encoding="utf-8")
    grounding = production_root / "grounding" / "production-manifest.json"
    grounding.write_text(
        json.dumps({"schema": "autodata.grounding/v1", "tasks": []}),
        encoding="utf-8",
    )
    grounding_ref = {
        "manifest_path": "grounding/production-manifest.json",
        "digest": "sha256:" + hashlib.sha256(grounding.read_bytes()).hexdigest(),
    }
    meta_row = {
        "id": meta_id,
        "status": "completed",
        "phase": "completed",
        "winnerCandidateId": "cand-one",
        "pipelineRoot": str(run_root),
        "executionJson": json.dumps(
            {
                "mode": "meta_optimize",
                "split_seed": 20261008,
                "executor": {},
                "secret_references": ["AAR_AUTODATA_CAPABILITY"],
            }
        ),
    }
    production_row = {
        "id": production_id,
        "status": "active",
        "phase": "baseline_pending",
        "executionJson": json.dumps({"mode": "production"}),
    }
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_native_subject",
        lambda _state, _kind, subject_id: (
            meta_row if subject_id == meta_id else production_row
        ),
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_run_binding",
        lambda *_: (
            lifecycle_supervisor._registration_entry(
                control, kind="workspace", subject_id=workspace_id
            ),
            bootstrap,
            run_root,
        ),
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_execution_finalization",
        lambda *_: {
            "winner_candidate_id": "cand-one",
            "winner_tree_digest": "sha256:" + "b" * 64,
            "test_evaluation": {
                "candidate_id": "cand-one",
                "constraints": {"valid": True},
            },
        },
    )
    monkeypatch.setattr(
        lifecycle_supervisor, "_trusted_execution_settings", lambda **_: settings
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "canonical_meta_manifest_from_default",
        lambda **_: json.loads(str(meta_row["executionJson"])),
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_study_reserved_task_ids",
        lambda *_: [f"task-{index:03d}" for index in range(128)],
    )
    monkeypatch.setattr(lifecycle_supervisor, "_export_winner_idempotently", lambda *_, **__: None)
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_copy_tree_with_production_grounding",
        lambda **_: (pipeline, grounding_ref),
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "canonical_production_manifest_from_meta",
        lambda **_: {"schema": "autodata.execution/v1", "mode": "production"},
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "validate_generation_inputs",
        lambda **_: {"schema": "aar.autodata.training-data-contract/v1"},
    )
    monkeypatch.setattr(
        lifecycle_supervisor, "execution_creation_key", lambda *_, **__: "key-one"
    )
    native_calls = 0

    def native(*_: object) -> dict[str, str]:
        nonlocal native_calls
        native_calls += 1
        return {"execution_id": production_id}

    monkeypatch.setattr(lifecycle_supervisor, "_native_cli", native)
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_equivalent_executions",
        lambda *_: [{"id": production_id}],
    )
    monkeypatch.setattr(
        lifecycle_supervisor, "_execution_study", lambda *_: "study-one"
    )
    monkeypatch.setattr(lifecycle_supervisor, "snapshot_database", lambda *_, **__: True)
    args = Namespace(
        state=tmp_path / "state.db",
        retained_state=retained,
        control_file=control,
        artifacts=artifacts,
        workspaces=workspaces,
        python=Path(sys.executable),
        campaign_policy=tmp_path / "policy.json",
        training_data_contract=tmp_path / "contract.json",
        resolved_config=tmp_path / "resolved.yaml",
        resolved_config_sha256=None,
        campaign_policy_sha256=None,
    )

    first = lifecycle_supervisor.reconcile_completed_meta_execution(args, meta_id)
    second = lifecycle_supervisor.reconcile_completed_meta_execution(args, meta_id)

    assert first["production_execution_id"] == production_id
    assert second["production_execution_id"] == production_id
    assert native_calls == 2
    subjects = lifecycle_supervisor._load_control(control)["subjects"]
    assert sum(entry["subject_id"] == production_id for entry in subjects) == 1
    assert (run_root / "supervised-transition-intent.json").is_file()


@pytest.mark.parametrize(
    "test_evaluation",
    [
        None,
        {"candidate_id": "different", "constraints": {"valid": True}},
        {"candidate_id": "cand-one"},
        {"candidate_id": "cand-one", "constraints": {"valid": False}},
    ],
)
def test_completed_meta_transition_rejects_invalid_final_test_evidence_before_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_evaluation: object,
) -> None:
    meta_id = "exe_" + "2" * 32
    export_calls: list[str] = []
    native_calls: list[str] = []
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_native_subject",
        lambda *_: {
            "status": "completed",
            "phase": "completed",
            "winnerCandidateId": "cand-one",
            "executionJson": json.dumps({"mode": "meta_optimize"}),
        },
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_run_binding",
        lambda *_: ({}, {"study_id": "study-one"}, tmp_path),
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_execution_finalization",
        lambda *_: {
            "winner_candidate_id": "cand-one",
            "winner_tree_digest": "sha256:" + "b" * 64,
            "test_evaluation": test_evaluation,
        },
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_export_winner_idempotently",
        lambda *_, **__: export_calls.append("export"),
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_native_cli",
        lambda *_, **__: native_calls.append("native"),
    )
    args = Namespace(
        state=tmp_path / "state.db", control_file=tmp_path / "control.json"
    )

    with pytest.raises(RuntimeError, match="lacks valid winner test evidence"):
        lifecycle_supervisor.reconcile_completed_meta_execution(args, meta_id)

    assert export_calls == []
    assert native_calls == []


def _production_attainability_fixture(
    tmp_path: Path,
    results: list[tuple[str, str, bool, str | None]],
    *,
    required_rows: int = 3,
    source_count: int = 5,
) -> tuple[Path, Path, str]:
    state = tmp_path / "state.db"
    artifacts = tmp_path / "artifacts"
    pipeline = tmp_path / "pipeline"
    (artifacts / "objects" / "sha256").mkdir(parents=True)
    (pipeline / "grounding").mkdir(parents=True)
    source_ids = [f"source-{index}" for index in range(source_count)]
    manifest = pipeline / "grounding" / "production.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "autodata.grounding/v1",
                "tasks": [{"id": task_id} for task_id in source_ids],
            }
        ),
        encoding="utf-8",
    )
    manifest_digest = "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()
    execution_id = "exe_production"
    spec = {
        "mode": "production",
        "grounding": {
            "manifest_path": "grounding/production.json",
            "digest": manifest_digest,
        },
        "finalization": {"minimum_generated_items": required_rows},
    }
    with sqlite3.connect(state) as connection:
        connection.executescript(
            """
            CREATE TABLE executions (
              id TEXT PRIMARY KEY, executionJson TEXT, pipelineRoot TEXT
            );
            CREATE TABLE events (
              scopeKind TEXT, scopeId TEXT, kind TEXT, payloadJson TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?)",
            (execution_id, json.dumps(spec), str(pipeline)),
        )
        for task_id, phase, accepted, reason_code in results:
            task_result = {
                "task_id": task_id,
                "outcome": "succeeded",
                "generated_items": ([{"row": task_id}] if accepted else []),
                "reason_code": reason_code,
            }
            encoded = json.dumps(task_result, sort_keys=True).encode()
            digest = hashlib.sha256(encoded).hexdigest()
            artifact = artifacts / "objects" / "sha256" / digest[:2] / digest[2:]
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(encoded)
            connection.execute(
                "INSERT INTO events VALUES (?,?,?,?)",
                (
                    "execution",
                    execution_id,
                    "task_attempt.completed",
                    json.dumps(
                        {
                            "task_id": task_id,
                            "phase": phase,
                            "artifact": {
                                "digest": f"sha256:{digest}",
                                "size": len(encoded),
                            },
                        }
                    ),
                ),
            )
    return state, artifacts, execution_id


@pytest.mark.parametrize(
    ("results", "required_rows", "expected_maximum", "attainable"),
    [
        # Healthy: one accepted, one first-pass empty but retryable, and three
        # unfinished/in-flight source tasks.
        (
            [
                ("source-0", "final-full-corpus", True, None),
                ("source-1", "final-full-corpus", False, "target_not_challenging"),
            ],
            4,
            5,
            True,
        ),
        # Boundary equality must continue after two sources have exhausted
        # their one native retry.
        (
            [
                ("source-0", "final-full-corpus", True, None),
                ("source-1", "final-full-corpus-retry-2", False, "judge_rejected"),
                ("source-2", "final-full-corpus-retry-2", False, "judge_rejected"),
            ],
            3,
            3,
            True,
        ),
        # Once three distinct source IDs have provably exhausted retry, at most
        # two rows remain possible regardless of provider/native attempt count.
        (
            [
                ("source-0", "final-full-corpus-retry-2", False, "judge_rejected"),
                ("source-1", "final-full-corpus-retry-2", False, "judge_rejected"),
                ("source-2", "final-full-corpus-retry-2", False, "judge_rejected"),
            ],
            3,
            2,
            False,
        ),
    ],
)
def test_production_acceptance_attainability_is_conservative_per_source(
    tmp_path: Path,
    results: list[tuple[str, str, bool, str | None]],
    required_rows: int,
    expected_maximum: int,
    attainable: bool,
) -> None:
    state, artifacts, execution_id = _production_attainability_fixture(
        tmp_path, results, required_rows=required_rows
    )

    status = lifecycle_supervisor._production_acceptance_attainability(
        state, artifacts, execution_id
    )

    assert status["maximum_possible_rows"] == expected_maximum
    assert status["attainable"] is attainable
    if attainable:
        lifecycle_supervisor._require_production_acceptance_attainability(
            state, artifacts, execution_id
        )
    else:
        with pytest.raises(
            lifecycle_supervisor.NativeStepFailure,
            match="accepted-row requirement is unattainable",
        ):
            lifecycle_supervisor._require_production_acceptance_attainability(
                state, artifacts, execution_id
            )


def test_production_first_empty_result_remains_retry_eligible(
    tmp_path: Path,
) -> None:
    state, artifacts, execution_id = _production_attainability_fixture(
        tmp_path,
        [("source-0", "final-full-corpus", False, "target_not_challenging")],
        required_rows=5,
    )

    status = lifecycle_supervisor._production_acceptance_attainability(
        state, artifacts, execution_id
    )

    assert status["retry_eligible_or_unfinished_tasks"] == 5
    assert status["maximum_possible_rows"] == 5
    assert status["attainable"] is True


def test_production_in_flight_source_remains_attainable(tmp_path: Path) -> None:
    state, artifacts, execution_id = _production_attainability_fixture(
        tmp_path, [], required_rows=5
    )
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO events VALUES (?,?,?,?)",
            (
                "execution",
                execution_id,
                "task_attempt.submitted",
                json.dumps(
                    {"task_id": "source-0", "phase": "final-full-corpus"}
                ),
            ),
        )

    status = lifecycle_supervisor._production_acceptance_attainability(
        state, artifacts, execution_id
    )

    assert status["retry_eligible_or_unfinished_tasks"] == 5
    assert status["maximum_possible_rows"] == 5
    assert status["attainable"] is True


@pytest.mark.parametrize(
    ("meta_status", "production_registration"),
    [
        ("registered", None),
        (
            "registered",
            {
                "kind": "execution",
                "subject_id": "exe_" + "3" * 32,
                "status": "registered",
            },
        ),
        (
            "registered",
            {
                "kind": "execution",
                "subject_id": "exe_" + "3" * 32,
                "status": "registered",
                "parent_meta_execution_id": "exe_" + "2" * 32,
            },
        ),
    ],
)
def test_completed_meta_transition_recovers_every_registration_crash_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    meta_status: str,
    production_registration: dict[str, object] | None,
) -> None:
    workspace_id = "ws_" + "1" * 32
    meta_id = "exe_" + "2" * 32
    production_id = "exe_" + "3" * 32
    subjects: list[dict[str, object]] = [
        {
            "kind": "workspace",
            "subject_id": workspace_id,
            "status": "completed",
            "canonical_execution_id": meta_id,
        },
        {
            "kind": "execution",
            "subject_id": meta_id,
            "status": meta_status,
            "production_execution_id": production_id,
        },
    ]
    if production_registration is not None:
        subjects.append(production_registration)
    control = tmp_path / "control.json"
    lifecycle_supervisor._atomic_json(
        control,
        {"schema": lifecycle_supervisor.CONTROL_SCHEMA, "subjects": subjects},
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_native_subject",
        lambda *_: {
            "status": "completed",
            "phase": "completed",
            "executionJson": json.dumps({"mode": "meta_optimize"}),
        },
    )
    recovered: list[str] = []

    def reconcile(_args: Namespace, execution_id: str) -> dict[str, str]:
        recovered.append(execution_id)
        return {"transition": "meta-to-production"}

    monkeypatch.setattr(
        lifecycle_supervisor, "reconcile_completed_meta_execution", reconcile
    )
    args = Namespace(state=tmp_path / "state.db", control_file=control)
    result = lifecycle_supervisor.reconcile_completed_execution_transition(args)
    assert result == {"transition": "meta-to-production"}
    assert recovered == [meta_id]


def test_completed_production_publishes_one_verified_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aar.infrastructure import autodata_lifecycle

    run_root = tmp_path / "team" / "autodata" / "run-one"
    winner = run_root / "meta-winner"
    production = run_root / "production" / "grounding"
    winner.mkdir(parents=True)
    production.mkdir(parents=True)
    production_manifest = production / "production-manifest.json"
    production_manifest.write_text("{}", encoding="utf-8")
    intent = run_root / "supervised-transition-intent.json"
    lifecycle_supervisor._atomic_json(intent, {"schema": "intent"})
    intent_digest = "sha256:" + hashlib.sha256(intent.read_bytes()).hexdigest()
    retained = tmp_path / "retained.db"
    retained.write_bytes(b"retained")
    control = tmp_path / "control.json"
    workspace_id = "ws_" + "1" * 32
    meta_id = "exe_" + "2" * 32
    production_id = "exe_" + "3" * 32
    lifecycle_supervisor._atomic_json(
        control,
        {
            "schema": lifecycle_supervisor.CONTROL_SCHEMA,
            "subjects": [
                {
                    "kind": "workspace",
                    "subject_id": workspace_id,
                    "status": "completed",
                    "canonical_execution_id": meta_id,
                },
                {
                    "kind": "execution",
                    "subject_id": meta_id,
                    "status": "completed",
                    "production_execution_id": production_id,
                },
                {
                    "kind": "execution",
                    "subject_id": production_id,
                    "status": "registered",
                    "parent_meta_execution_id": meta_id,
                    "transition_intent_sha256": intent_digest,
                },
            ],
        },
    )
    bootstrap = {
        "run_id": "run-one",
        "workspace_id": workspace_id,
        "study_id": "study-one",
    }
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_run_binding",
        lambda *_: ({}, bootstrap, run_root),
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_native_subject",
        lambda *_: {
            "status": "completed",
            "phase": "completed",
            "executionJson": json.dumps({"mode": "production"}),
        },
    )
    monkeypatch.setattr(
        lifecycle_supervisor, "_execution_study", lambda *_: "study-one"
    )
    dataset_bytes = b'{"schema":"autodata.dataset/v1"}\n'
    dataset_digest = "sha256:" + hashlib.sha256(dataset_bytes).hexdigest()
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_execution_finalization",
        lambda *_: {"dataset": {"digest": dataset_digest}},
    )
    monkeypatch.setattr(lifecycle_supervisor, "snapshot_database", lambda *_, **__: True)

    def export_dataset(
        _args: Namespace, *, execution_id: str, destination: Path, expected_digest: str
    ) -> None:
        assert execution_id == production_id
        assert expected_digest == dataset_digest
        if not destination.exists():
            destination.write_bytes(dataset_bytes)

    monkeypatch.setattr(
        lifecycle_supervisor, "_export_dataset_idempotently", export_dataset
    )
    verification_calls = 0

    def publish(run_id: str) -> dict[str, object]:
        nonlocal verification_calls
        verification_calls += 1
        assert run_id == "run-one"
        marker = run_root / "training-handoff.verified.json"
        if not marker.exists():
            marker.write_text("{}", encoding="utf-8")
        return {
            "meta_execution_id": meta_id,
            "production_execution_id": production_id,
            "available_rows": 1000,
            "verified_marker": str(marker),
        }

    monkeypatch.setattr(
        autodata_lifecycle, "publish_verified_handoff_marker", publish
    )
    args = Namespace(
        state=tmp_path / "state.db",
        retained_state=retained,
        control_file=control,
        artifacts=tmp_path / "artifacts",
        workspaces=tmp_path / "workspaces",
        python=Path(sys.executable),
    )

    first = lifecycle_supervisor.reconcile_completed_production_execution(
        args, production_id
    )
    second = lifecycle_supervisor.reconcile_completed_production_execution(
        args, production_id
    )

    assert first == second
    assert verification_calls == 2
    handoff = json.loads((run_root / "training-handoff.json").read_text())
    assert handoff["state_db"] == str(retained)
    assert handoff["production_execution_id"] == production_id
    assert handoff["consumption_receipt"] == str(
        run_root / "training-consumption.json"
    )


def test_snapshot_removes_stale_retained_sidecars(tmp_path: Path) -> None:
    live = tmp_path / "live.db"
    retained = tmp_path / "retained.db"
    _state(live)
    _state(retained)
    wal = Path(f"{retained}-wal")
    shm = Path(f"{retained}-shm")
    wal.write_bytes(b"stale wal")
    shm.write_bytes(b"stale shm")

    assert snapshot_database(live, retained, reason="replace-stale") is True

    assert not wal.exists()
    assert not shm.exists()
    with sqlite3.connect(f"file:{retained}?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]


def test_restore_ignores_untrusted_retained_sidecars(tmp_path: Path) -> None:
    live = tmp_path / "live.db"
    retained = tmp_path / "retained.db"
    restored = tmp_path / "restored.db"
    _state(live)
    snapshot_database(live, retained, reason="valid-main")
    Path(f"{retained}-wal").write_bytes(b"not a sqlite wal")
    Path(f"{retained}-shm").write_bytes(b"not sqlite shared memory")

    assert restore_database(retained, restored, require_manifest=True) is True

    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("durable",)


def test_restore_rejects_snapshot_digest_mismatch(tmp_path: Path) -> None:
    live = tmp_path / "live.db"
    retained = tmp_path / "retained.db"
    _state(live)
    snapshot_database(live, retained, reason="valid")
    metadata_path = retained.with_name("retained.db.snapshot.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(RuntimeError, match="snapshot digest"):
        restore_database(retained, tmp_path / "restored.db")


def test_supervised_restore_rejects_retained_database_without_manifest(
    tmp_path: Path,
) -> None:
    retained = tmp_path / "retained.db"
    _state(retained)
    with pytest.raises(RuntimeError, match="missing its snapshot manifest"):
        restore_database(
            retained, tmp_path / "restored.db", require_manifest=True
        )


def test_snapshot_rejects_foreign_key_violation(tmp_path: Path) -> None:
    live = tmp_path / "invalid.db"
    with sqlite3.connect(live) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE parent (id INTEGER PRIMARY KEY);
            CREATE TABLE child (
              id INTEGER PRIMARY KEY,
              parent_id INTEGER REFERENCES parent(id)
            );
            INSERT INTO child VALUES (1, 999);
            """
        )
    with pytest.raises(RuntimeError, match="foreign_key_check"):
        snapshot_database(live, tmp_path / "retained.db", reason="invalid")


def test_restore_accepts_previous_digest_during_atomic_publish_transition(
    tmp_path: Path,
) -> None:
    live = tmp_path / "live.db"
    retained = tmp_path / "retained.db"
    _state(live)
    snapshot_database(live, retained, reason="first")
    previous = hashlib.sha256(retained.read_bytes()).hexdigest()
    metadata_path = retained.with_name("retained.db.snapshot.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["sha256"] = "1" * 64
    metadata["previous_sha256"] = previous
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    assert restore_database(retained, tmp_path / "restored.db") is True


def test_next_subject_pauses_for_actions_and_uses_phase_timeouts(tmp_path: Path) -> None:
    state = tmp_path / "state.db"
    control = tmp_path / "control.json"
    _state(state)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_unused_default",
                "active",
                "baseline_pending",
                "2025-01-01",
                json.dumps({"mode": "meta_optimize"}),
                6300,
            ),
        )
        connection.execute(
            "INSERT INTO workspaces VALUES (?,?,?,?,?)",
            ("ws_one", "active", "grounding_review", "2026-01-01", 6300),
        )
        connection.execute(
            "INSERT INTO actions VALUES (?,?,?)",
            ("workspace", "ws_one", "pending"),
        )
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_prod",
                "active",
                "baseline_pending",
                "2026-01-02",
                json.dumps({"mode": "production"}),
                28200,
            ),
        )
    register_subject(state, control, kind="workspace", subject_id="ws_one")
    register_subject(state, control, kind="execution", subject_id="exe_prod")

    subject = next_subject(state, control)
    assert subject is not None
    assert subject.subject_id == "exe_prod"
    assert subject.subject_id != "exe_unused_default"
    assert subject.timeout_seconds == PRODUCTION_TIMEOUT_SECONDS
    assert subject.stall_seconds == PRODUCTION_STALL_SECONDS

    with sqlite3.connect(state) as connection:
        connection.execute("UPDATE actions SET status='in_progress'")
    subject = next_subject(state, control)
    assert subject is not None
    assert subject.subject_id == "exe_prod"

    with sqlite3.connect(state) as connection:
        connection.execute("UPDATE actions SET status='completed'")
    subject = next_subject(state, control)
    assert subject is not None
    assert subject.subject_id == "ws_one"
    assert subject.timeout_seconds == META_TIMEOUT_SECONDS
    assert subject.stall_seconds == META_STALL_SECONDS


def test_observe_only_subject_keeps_stall_detection_without_elapsed_timeout(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.db"
    control = tmp_path / "control.json"
    _state(state)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_observe",
                "active",
                "baseline_pending",
                "2026-01-01",
                json.dumps({"mode": "production"}),
                604800,
            ),
        )
    register_subject(state, control, kind="execution", subject_id="exe_observe")

    subject = next_subject(state, control, stage_timeout_policy="observe-only")

    assert subject is not None
    assert subject.timeout_seconds is None
    assert subject.stall_seconds == PRODUCTION_STALL_SECONDS


def test_next_subject_rejects_native_budget_without_controller_grace(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.db"
    control = tmp_path / "control.json"
    _state(state)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_meta",
                "active",
                "baseline_pending",
                "2026-01-01",
                json.dumps({"mode": "meta_optimize"}),
                META_TIMEOUT_SECONDS,
            ),
        )
    register_subject(state, control, kind="execution", subject_id="exe_meta")
    with pytest.raises(RuntimeError, match="plus grace"):
        next_subject(state, control)


def test_next_subject_accepts_explicit_long_production_controller_timeout(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.db"
    control = tmp_path / "control.json"
    _state(state)
    native_wall = 24 * 60 * 60
    controller_timeout = 25 * 60 * 60
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_long_production",
                "active",
                "final_pending",
                "2026-01-01",
                json.dumps({"mode": "production"}),
                native_wall,
            ),
        )
    register_subject(
        state,
        control,
        kind="execution",
        subject_id="exe_long_production",
    )

    subject = next_subject(
        state,
        control,
        production_timeout_seconds=controller_timeout,
    )

    assert subject is not None
    assert subject.timeout_seconds == controller_timeout
    assert subject.production is True


def test_unregistered_active_subject_is_never_selected(tmp_path: Path) -> None:
    state = tmp_path / "state.db"
    _state(state)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_default",
                "active",
                "baseline_pending",
                "2026-01-01",
                json.dumps({"mode": "meta_optimize"}),
                6300,
            ),
        )
    assert next_subject(state, tmp_path / "missing-control.json") is None


def test_registration_is_idempotent_and_rejects_terminal_or_missing_subjects(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.db"
    control = tmp_path / "control.json"
    _state(state)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO workspaces VALUES (?,?,?,?,?)",
            ("ws_chosen", "active", "pipeline_pending", "2026-01-01", 6300),
        )
        connection.execute(
            "INSERT INTO workspaces VALUES (?,?,?,?,?)",
            ("ws_frozen", "frozen", "frozen", "2026-01-02", 6300),
        )

    first = register_subject(state, control, kind="workspace", subject_id="ws_chosen")
    second = register_subject(state, control, kind="workspace", subject_id="ws_chosen")
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    with pytest.raises(RuntimeError, match="already frozen"):
        register_subject(state, control, kind="workspace", subject_id="ws_frozen")
    with pytest.raises(RuntimeError, match="does not exist"):
        register_subject(state, control, kind="execution", subject_id="exe_missing")


def test_registration_rejects_semantic_duplicate_execution(tmp_path: Path) -> None:
    state = tmp_path / "state.db"
    control = tmp_path / "control.json"
    _state(state)
    spec = json.dumps({"mode": "production", "split_seed": 7})
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            ("exe_primary", "active", "final_pending", "2026-01-01", spec, 6300),
        )
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            ("exe_duplicate", "active", "final_pending", "2026-01-02", spec, 6300),
        )

    registered = register_subject(
        state, control, kind="execution", subject_id="exe_primary"
    )
    assert registered["subject_id"] == "exe_primary"
    with pytest.raises(RuntimeError, match="duplicates canonical execution exe_primary"):
        register_subject(
            state, control, kind="execution", subject_id="exe_duplicate"
        )


def test_execution_creation_key_is_content_bound_and_ignores_retry_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline_root = tmp_path / "pipeline"
    pipeline_root.mkdir()
    pipeline = pipeline_root / "autodata.pipeline.json"
    pipeline.write_text(json.dumps({"schema": "pipeline/v1", "name": "test"}))
    (pipeline_root / "recipe.py").write_text("VALUE = 1\n")
    execution = tmp_path / "execution.json"
    execution.write_text(json.dumps({"schema": "execution/v1", "mode": "production"}))
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()

    monkeypatch.setenv("AD_VER", "prod")
    first = execution_creation_key(
        pipeline, execution, study_id="study_one", workspaces=workspaces
    )
    monkeypatch.setenv("AD_VER", "prod2")
    second = execution_creation_key(
        pipeline, execution, study_id="study_one", workspaces=workspaces
    )
    assert first == second
    assert first.startswith("aar-supervised:")

    (pipeline_root / "recipe.py").write_text("VALUE = 2\n")
    changed = execution_creation_key(
        pipeline, execution, study_id="study_one", workspaces=workspaces
    )
    assert changed != first


def test_supervised_creation_reuses_and_cancels_unstarted_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state.db"
    retained = tmp_path / "retained.db"
    control = tmp_path / "control.json"
    artifacts = tmp_path / "artifacts"
    workspaces = tmp_path / "workspaces"
    pipeline_root = tmp_path / "pipeline"
    for path in (artifacts, workspaces, pipeline_root):
        path.mkdir()
    pipeline = pipeline_root / "autodata.pipeline.json"
    pipeline.write_text(json.dumps({"schema": "pipeline/v1", "name": "test"}))
    execution = tmp_path / "execution.json"
    spec = {"schema": "execution/v1", "mode": "production"}
    execution.write_text(json.dumps(spec))
    _state(state)
    stored_spec = json.dumps(spec)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_primary",
                "active",
                "final_pending",
                "2026-01-01",
                stored_spec,
                6300,
            ),
        )

    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        lifecycle_supervisor,
        "validate_generation_inputs",
        lambda **_: {"schema": "aar.autodata.training-data-contract/v1"},
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_trusted_execution_settings",
        lambda **_: {"concurrency": 32},
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "canonical_execution_manifest",
        lambda **_: spec,
    )

    def fake_native_cli(*args: object) -> dict[str, object]:
        arguments = tuple(str(value) for value in args[4:])
        calls.append(arguments)
        if arguments[:2] == ("execution", "create"):
            with sqlite3.connect(state) as connection:
                connection.execute(
                    "INSERT INTO executions VALUES (?,?,?,?,?,?)",
                    (
                        "exe_duplicate",
                        "active",
                        "baseline_pending",
                        "2026-01-02",
                        stored_spec,
                        6300,
                    ),
                )
            return {"execution_id": "exe_duplicate", "status": "active"}
        assert arguments == ("cancel", "exe_duplicate")
        with sqlite3.connect(state) as connection:
            connection.execute(
                "UPDATE executions SET status='cancelled',phase='cancelled' "
                "WHERE id='exe_duplicate'"
            )
        return {"execution_id": "exe_duplicate", "status": "cancelled"}

    monkeypatch.setattr(lifecycle_supervisor, "_native_cli", fake_native_cli)
    result = create_or_reuse_execution(
        python=Path(sys.executable),
        state=state,
        retained_state=retained,
        control_file=control,
        artifacts=artifacts,
        workspaces=workspaces,
        pipeline=pipeline,
        execution=execution,
        study_id="study_one",
        training_data_contract=tmp_path / "contract.json",
        campaign_policy=tmp_path / "policy.json",
    )

    assert result["execution_id"] == "exe_primary"
    assert result["deduplicated"] is True
    assert result["discarded_duplicate_execution_id"] == "exe_duplicate"
    assert calls[0][:2] == ("execution", "create")
    assert calls[1] == ("cancel", "exe_duplicate")
    assert retained.is_file()
    subjects = json.loads(control.read_text(encoding="utf-8"))["subjects"]
    assert [entry["subject_id"] for entry in subjects] == ["exe_primary"]


def test_supervised_creation_rejects_before_native_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("artifacts", "workspaces", "pipeline"):
        (tmp_path / name).mkdir()
    pipeline = tmp_path / "pipeline" / "autodata.pipeline.json"
    pipeline.write_text("{}", encoding="utf-8")
    execution = tmp_path / "execution.json"
    execution.write_text(
        json.dumps(
            {
                "schema": "autodata.execution/v1",
                "mode": "meta_optimize",
                "budget": {"max_iterations": 1, "min_iterations": 0},
                "tuning_task_ids": [],
                "validation_task_ids": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "_trusted_execution_settings",
        lambda **_: {"concurrency": 32},
    )
    monkeypatch.setattr(
        lifecycle_supervisor,
        "canonical_execution_manifest",
        lambda **_: (_ for _ in ()).throw(ValueError("wrong meta budget")),
    )
    native_called = False

    def fail_native(*_: object) -> dict[str, object]:
        nonlocal native_called
        native_called = True
        raise AssertionError("native CLI must not run")

    monkeypatch.setattr(lifecycle_supervisor, "_native_cli", fail_native)
    with pytest.raises(ValueError, match="wrong meta budget"):
        create_or_reuse_execution(
            python=Path(sys.executable),
            state=tmp_path / "state.db",
            retained_state=tmp_path / "retained.db",
            control_file=tmp_path / "control.json",
            artifacts=tmp_path / "artifacts",
            workspaces=tmp_path / "workspaces",
            pipeline=pipeline,
            execution=execution,
            study_id="study_one",
            training_data_contract=tmp_path / "contract.json",
            campaign_policy=tmp_path / "policy.json",
        )
    assert native_called is False


def test_register_cli_snapshots_before_publishing_control(tmp_path: Path) -> None:
    state = tmp_path / "live" / "state.db"
    state.parent.mkdir()
    retained = tmp_path / "retained" / "state.db"
    control = tmp_path / "retained" / "control.json"
    _state(state)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO workspaces VALUES (?,?,?,?,?)",
            ("ws_cli", "active", "pipeline_pending", "2026-01-01", 6300),
        )
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "autodata_lifecycle_supervisor.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "register",
            "--state",
            str(state),
            "--retained-state",
            str(retained),
            "--control-file",
            str(control),
            "--subject-kind",
            "workspace",
            "--subject-id",
            "ws_cli",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout)["registered"] is True
    assert retained.is_file()
    assert retained.with_name("state.db.snapshot.json").is_file()
    assert json.loads(control.read_text(encoding="utf-8"))["subjects"][0][
        "subject_id"
    ] == "ws_cli"


def test_registered_completion_is_reconciled_but_missing_registration_fails(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state.db"
    control = tmp_path / "control.json"
    _state(state)
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES (?,?,?,?,?,?)",
            (
                "exe_chosen",
                "active",
                "final_pending",
                "2026-01-01",
                json.dumps({"mode": "meta_optimize"}),
                6300,
            ),
        )
    register_subject(state, control, kind="execution", subject_id="exe_chosen")
    with sqlite3.connect(state) as connection:
        connection.execute(
            "UPDATE executions SET status='completed',phase='completed' WHERE id=?",
            ("exe_chosen",),
        )
    assert next_subject(state, control) is None
    registration = json.loads(control.read_text(encoding="utf-8"))["subjects"][0]
    assert registration["status"] == "completed"
    assert registration["native_status"] == "completed"

    registration["subject_id"] = "exe_vanished"
    registration["status"] = "registered"
    registration.pop("native_status")
    control.write_text(
        json.dumps({"schema": "aar.autodata.lifecycle-control/v1", "subjects": [registration]}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="is missing"):
        next_subject(state, control)
