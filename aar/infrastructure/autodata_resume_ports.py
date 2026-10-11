"""Resolve job-local AutoData ports that must survive a chain-session retry."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _loopback_port(raw: Any, label: str) -> int:
    if not isinstance(raw, str):
        raise RuntimeError(f"{label} is missing from the retained workspace")
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.port is None
    ):
        raise RuntimeError(f"{label} is not a safe loopback endpoint")
    return parsed.port


def _workspace_spec(
    connection: sqlite3.Connection, *, workspace_id: str | None = None
) -> dict[str, Any] | None:
    if workspace_id is None:
        rows = connection.execute(
            "SELECT specJson FROM workspaces WHERE status='active' "
            "ORDER BY updatedAt DESC,id DESC"
        ).fetchall()
        if len(rows) > 1:
            raise RuntimeError("retained AutoData state has ambiguous active workspaces")
    else:
        rows = connection.execute(
            "SELECT specJson FROM workspaces WHERE id=?", (workspace_id,)
        ).fetchall()
        if len(rows) != 1:
            raise RuntimeError(
                f"supervised AutoData workspace {workspace_id} is missing"
            )
    row = rows[0] if rows else None
    if row is None:
        return None
    try:
        value = json.loads(str(row[0]))
    except json.JSONDecodeError as error:
        raise RuntimeError("retained AutoData workspace has invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("retained AutoData workspace is not an object")
    return value


def _supervised_workspace_id(control: Path) -> str | None:
    if control.is_symlink():
        raise RuntimeError("AutoData lifecycle control must not be a symlink")
    if not control.exists():
        return None
    try:
        value = json.loads(control.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("AutoData lifecycle control is unavailable") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "subjects"}
        or value.get("schema") != "aar.autodata.lifecycle-control/v1"
    ):
        raise RuntimeError("AutoData lifecycle control has an invalid schema")
    subjects = value.get("subjects")
    if not isinstance(subjects, list):
        raise RuntimeError("AutoData lifecycle control has no subjects array")
    workspaces = [
        entry
        for entry in subjects
        if isinstance(entry, dict) and entry.get("kind") == "workspace"
    ]
    if not workspaces:
        return None
    if len(workspaces) != 1:
        raise RuntimeError("AutoData lifecycle control has ambiguous workspaces")
    workspace = workspaces[0]
    workspace_id = workspace.get("subject_id")
    status = workspace.get("status")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise RuntimeError("AutoData lifecycle workspace has no identifier")
    if status not in {"registered", "completed"}:
        raise RuntimeError("AutoData lifecycle workspace has invalid status")
    canonical_id = workspace.get("canonical_execution_id")
    if status == "completed":
        matches = [
            entry
            for entry in subjects
            if isinstance(entry, dict)
            and entry.get("kind") == "execution"
            and entry.get("subject_id") == canonical_id
            and entry.get("status") in {"registered", "completed"}
        ]
        if not isinstance(canonical_id, str) or not canonical_id or len(matches) != 1:
            raise RuntimeError(
                "completed AutoData workspace has no unique canonical execution"
            )
    return workspace_id


def resolve_resume_ports(
    state: Path, control: Path | None = None
) -> dict[str, int | None]:
    """Return retained loopback ports for the supervised workspace lineage."""
    if state.is_symlink() or not state.is_file():
        return {"broker_port": None, "generator_bridge_port": None}
    workspace_id = _supervised_workspace_id(control) if control is not None else None
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        if control is not None and workspace_id is None:
            retained_workspaces = int(
                connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
            )
            if retained_workspaces:
                raise RuntimeError(
                    "retained AutoData workspaces exist without lifecycle control"
                )
        spec = _workspace_spec(connection, workspace_id=workspace_id)
    if spec is None:
        return {"broker_port": None, "generator_bridge_port": None}
    executor = spec.get("authoring_executor")
    if not isinstance(executor, dict):
        raise RuntimeError("retained workspace has no authoring executor")
    environment = executor.get("non_secret_env")
    if not isinstance(environment, dict):
        raise RuntimeError("retained workspace has no executor environment")
    broker_port = _loopback_port(executor.get("broker_url"), "broker_url")
    bridge_port = _loopback_port(
        environment.get("AUTODATA_GENERATOR_URL"),
        "AUTODATA_GENERATOR_URL",
    )
    if broker_port == bridge_port:
        raise RuntimeError("retained AutoData loopback ports collide")
    return {
        "broker_port": broker_port,
        "generator_bridge_port": bridge_port,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--control", type=Path)
    args = parser.parse_args()
    print(json.dumps(resolve_resume_ports(args.state, args.control), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
