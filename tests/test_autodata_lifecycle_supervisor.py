from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.autodata_lifecycle_supervisor as lifecycle_supervisor
from scripts.autodata_lifecycle_supervisor import (
    META_STALL_SECONDS,
    META_TIMEOUT_SECONDS,
    PRODUCTION_STALL_SECONDS,
    PRODUCTION_TIMEOUT_SECONDS,
    create_or_reuse_execution,
    execution_creation_key,
    next_subject,
    register_subject,
    restore_database,
    snapshot_database,
)


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
