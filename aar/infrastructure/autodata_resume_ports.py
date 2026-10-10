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


def _workspace_spec(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT specJson FROM workspaces WHERE status='active' "
        "ORDER BY updatedAt DESC,id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        row = connection.execute(
            "SELECT w.specJson FROM workspaces AS w "
            "JOIN executions AS e ON e.workspaceId=w.id "
            "WHERE e.status NOT IN ('completed','failed','cancelled') "
            "ORDER BY e.updatedAt DESC,e.id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    try:
        value = json.loads(str(row[0]))
    except json.JSONDecodeError as error:
        raise RuntimeError("retained AutoData workspace has invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("retained AutoData workspace is not an object")
    return value


def resolve_resume_ports(state: Path) -> dict[str, int | None]:
    """Return retained loopback ports for an active workspace or execution."""
    if state.is_symlink() or not state.is_file():
        return {"broker_port": None, "generator_bridge_port": None}
    with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
        spec = _workspace_spec(connection)
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
    args = parser.parse_args()
    print(json.dumps(resolve_resume_ports(args.state), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
