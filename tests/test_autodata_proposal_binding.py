"""Proposal-before-generation contracts for delegated native AutoData approval."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from aar.research_loop import autodata_approval


def _state(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE workspaces (id TEXT PRIMARY KEY, status TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO workspaces(id,status) VALUES (?,?)",
            [
                ("ws_" + "1" * 32, "active"),
                ("ws_" + "2" * 32, "active"),
            ],
        )
    return path


def _registry(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": autodata_approval.BINDINGS_SCHEMA,
                "proposals": {},
                "workspaces": {},
            }
        )
    )
    path.chmod(0o600)
    return path


def _marker(path: Path, *, code_hash: str = "a" * 64) -> Path:
    path.write_text(
        json.dumps(
            {
                "approved": True,
                "code_hash": code_hash,
                "idea_name": "method_one",
                "idea_uid": "chain-one",
                "run_id": "chain-one-method-one-1",
                "ts": 123.5,
            }
        )
    )
    return path


def _package(workspace: str, kind: str) -> dict[str, object]:
    return {
        "scope": {"kind": "workspace", "id": workspace, "revision": 2},
        "action_kind": kind,
    }


def test_grounding_refuses_before_approved_proposal(tmp_path: Path) -> None:
    state = _state(tmp_path / "state.db")
    registry = _registry(tmp_path / "bindings.json")
    with (
        mock.patch.dict(
            os.environ,
            {
                "AAR_AUTODATA_PROPOSAL_BINDINGS": str(registry),
                "IDEA_UID": "chain-one",
            },
            clear=False,
        ),
        mock.patch(
            "aar.research_loop.tools.server_api_tools._proposal_approved",
            return_value=(False, "no approved proposal"),
        ),
    ):
        with pytest.raises(RuntimeError, match="submit_idea_proposal approval first"):
            autodata_approval._proposal_binding(
                state, _package("ws_" + "1" * 32, "approve_grounding")
            )


def test_one_proposal_binds_one_live_workspace_and_all_later_gates(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path / "state.db")
    registry = _registry(tmp_path / "bindings.json")
    marker = _marker(tmp_path / "proposal.json")
    environment = {
        "AAR_AUTODATA_PROPOSAL_BINDINGS": str(registry),
        "IDEA_UID": "chain-one",
    }
    with (
        mock.patch.dict(os.environ, environment, clear=False),
        mock.patch(
            "aar.research_loop.tools.server_api_tools._proposal_approved",
            return_value=(True, "approved"),
        ),
        mock.patch(
            "aar.research_loop.tools.server_api_tools._proposal_marker_path",
            return_value=marker,
        ),
    ):
        workspace_one = "ws_" + "1" * 32
        workspace_two = "ws_" + "2" * 32
        binding = autodata_approval._proposal_binding(
            state, _package(workspace_one, "approve_grounding")
        )
        assert binding["run_id"] == "chain-one-method-one-1"
        assert autodata_approval._proposal_binding(
            state, _package(workspace_one, "approve_baseline")
        ) == binding
        assert autodata_approval._proposal_binding(
            state, _package(workspace_one, "approve_resources")
        ) == binding
        with pytest.raises(RuntimeError, match="already bound"):
            autodata_approval._proposal_binding(
                state, _package(workspace_two, "approve_grounding")
            )

        with sqlite3.connect(state) as connection:
            connection.execute(
                "UPDATE workspaces SET status='cancelled' WHERE id=?",
                (workspace_one,),
            )
        replacement = autodata_approval._proposal_binding(
            state, _package(workspace_two, "approve_grounding")
        )
        assert replacement["proposal_key"] == binding["proposal_key"]


def test_run9_prompt_and_launcher_require_proposal_binding() -> None:
    root = Path(__file__).resolve().parents[1]
    prompt = (root / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()
    submitter = (
        root
        / "experiments"
        / "dishonest_sycophancy_concealing"
        / "run_9"
        / "submit_run_9.sh"
    ).read_text()

    assert "Required AutoData ordering" in prompt
    assert "Only after it returns `approved: true` and a `run_id`" in prompt
    assert "aar.autodata.proposal-bindings/v1" in submitter
    assert 'chmod 600 "${proposal_bindings}"' in submitter
