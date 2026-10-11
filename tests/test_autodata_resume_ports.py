from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aar.infrastructure.autodata_resume_ports import resolve_resume_ports


def _state(path: Path, *, status: str = "active") -> Path:
    spec = {
        "authoring_executor": {
            "broker_url": "http://127.0.0.1:14993",
            "non_secret_env": {
                "AUTODATA_GENERATOR_URL": "http://127.0.0.1:54993/v1"
            },
        }
    }
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE workspaces(id TEXT,status TEXT,updatedAt TEXT,specJson TEXT);"
            "CREATE TABLE executions(id TEXT,workspaceId TEXT,status TEXT,updatedAt TEXT);"
        )
        connection.execute(
            "INSERT INTO workspaces VALUES('ws_1',?,?,?)",
            (status, "2026-01-01", json.dumps(spec)),
        )
    return path


def test_active_workspace_reuses_broker_and_generator_ports(tmp_path: Path) -> None:
    assert resolve_resume_ports(_state(tmp_path / "state.db")) == {
        "broker_port": 14993,
        "generator_bridge_port": 54993,
    }


def test_frozen_workspace_without_execution_workspace_id_reuses_ports(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path / "state.db", status="frozen")
    workspace_id = "ws_1"
    execution_id = "exe_1"
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES(?,?,?,?)",
            (execution_id, None, "active", "2026-01-02"),
        )
    control = tmp_path / "control.json"
    control.write_text(
        json.dumps(
            {
                "schema": "aar.autodata.lifecycle-control/v1",
                "subjects": [
                    {
                        "kind": "workspace",
                        "subject_id": workspace_id,
                        "status": "completed",
                        "canonical_execution_id": execution_id,
                    },
                    {
                        "kind": "execution",
                        "subject_id": execution_id,
                        "status": "registered",
                    },
                ]
            }
        )
    )
    assert resolve_resume_ports(state, control)["broker_port"] == 14993


def test_no_active_subject_has_no_retained_ports(tmp_path: Path) -> None:
    state = _state(tmp_path / "state.db", status="completed")
    assert resolve_resume_ports(state) == {
        "broker_port": None,
        "generator_bridge_port": None,
    }


def test_non_loopback_retained_endpoint_fails_closed(tmp_path: Path) -> None:
    state = _state(tmp_path / "state.db")
    with sqlite3.connect(state) as connection:
        spec = json.loads(
            connection.execute("SELECT specJson FROM workspaces").fetchone()[0]
        )
        spec["authoring_executor"]["broker_url"] = "https://example.com:443"
        connection.execute(
            "UPDATE workspaces SET specJson=?", (json.dumps(spec),)
        )
    with pytest.raises(RuntimeError, match="safe loopback"):
        resolve_resume_ports(state)


def test_completed_workspace_without_canonical_binding_fails_closed(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path / "state.db", status="frozen")
    control = tmp_path / "control.json"
    control.write_text(
        json.dumps(
            {
                "schema": "aar.autodata.lifecycle-control/v1",
                "subjects": [
                    {
                        "kind": "workspace",
                        "subject_id": "ws_1",
                        "status": "completed",
                    }
                ]
            }
        )
    )
    with pytest.raises(RuntimeError, match="unique canonical execution"):
        resolve_resume_ports(state, control)


def test_retained_workspace_without_control_fails_closed(tmp_path: Path) -> None:
    state = _state(tmp_path / "state.db", status="frozen")
    with pytest.raises(RuntimeError, match="without lifecycle control"):
        resolve_resume_ports(state, tmp_path / "missing-control.json")


def test_malformed_control_fails_closed(tmp_path: Path) -> None:
    state = _state(tmp_path / "state.db", status="frozen")
    control = tmp_path / "control.json"
    control.write_text("{}")
    with pytest.raises(RuntimeError, match="invalid schema"):
        resolve_resume_ports(state, control)


def test_empty_control_with_retained_workspace_fails_closed(tmp_path: Path) -> None:
    state = _state(tmp_path / "state.db", status="frozen")
    control = tmp_path / "control.json"
    control.write_text(
        json.dumps(
            {
                "schema": "aar.autodata.lifecycle-control/v1",
                "subjects": [],
            }
        )
    )
    with pytest.raises(RuntimeError, match="without lifecycle control"):
        resolve_resume_ports(state, control)
