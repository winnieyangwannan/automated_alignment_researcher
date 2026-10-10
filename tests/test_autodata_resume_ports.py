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


def test_active_execution_reuses_completed_workspace_ports(tmp_path: Path) -> None:
    state = _state(tmp_path / "state.db", status="completed")
    with sqlite3.connect(state) as connection:
        connection.execute(
            "INSERT INTO executions VALUES('exe_1','ws_1','active','2026-01-02')"
        )
    assert resolve_resume_ports(state)["broker_port"] == 14993


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
