"""Proposal-before-generation contracts for delegated native AutoData approval."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from aar.research_loop import autodata_approval
from aar.research_loop.tools import server_api_tools


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


def test_result_dedup_allows_retry_of_same_authoritative_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scores = tmp_path / "scores"
    scores.mkdir()
    monkeypatch.setenv("SCORES_DIR", str(scores))
    auth = {
        "model_fingerprint": "v1:test",
        "per_benchmark": {
            "public": {"mean": 0.5, "ci_low": 0.4, "ci_high": 0.6}
        },
    }

    first = server_api_tools._result_dedup(auth, None, "run-1")
    retry = server_api_tools._result_dedup(auth, "candidate", "run-1")
    duplicate = server_api_tools._result_dedup(auth, "other", "run-2")

    assert first == (True, None, None)
    assert retry == (True, None, None)
    assert duplicate[0] is False
    assert duplicate[1]["run_id"] == "run-1"


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
        / "launch"
        / "submit_full.sh"
    ).read_text()

    assert "Required AutoData ordering" in prompt
    assert "Only after it returns `approved: true` and a `run_id`" in prompt
    assert "every item has `id`, `prompt`, and `response`" in prompt
    assert (
        "Do not\nassume or access `instruction`, `answer`, or `thinking` fields"
        in prompt
    )
    assert "`prompt`,\n`chosen`, and `rejected`" in prompt
    assert "aar.autodata.proposal-bindings/v1" in submitter
    assert 'chmod 600 "${proposal_bindings}"' in submitter


def test_autodata_always_requires_explicit_proposal_run_id() -> None:
    with mock.patch.dict(os.environ, {"AAR_AUTODATA": "1"}, clear=True):
        assert server_api_tools._requires_explicit_proposal_run_id()
    with mock.patch.dict(os.environ, {"AAR_NO_LOCAL_GPU": "true"}, clear=True):
        assert server_api_tools._requires_explicit_proposal_run_id()
    with mock.patch.dict(
        os.environ,
        {"AAR_AUTODATA": "0", "AAR_NO_LOCAL_GPU": "false"},
        clear=True,
    ):
        assert not server_api_tools._requires_explicit_proposal_run_id()


def test_runtime_preserves_decoupled_run_id_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime = (root / "scripts" / "aar_runtime_env.sh").read_text()

    assert "AAR_NO_LOCAL_GPU" in runtime
    assert "AAR_AUTODATA_STATE" in runtime


def test_autodata_proposal_requires_receipt_producing_loader() -> None:
    direct_json = "payload = json.load(open(dataset_path))\n"
    assert "load_autodata_campaign_datasets" in (
        server_api_tools._autodata_method_contract_error(direct_json) or ""
    )

    wrong_size = """
load_autodata_campaign_datasets(
    [dataset_path],
    receipt_path=receipt_path,
    required_rows=64,
    expected_execution_ids=[execution_id],
    judge_rubric=training_data_contract["judge_rubric"],
    training_objective="sft",
)
"""
    assert server_api_tools._autodata_method_contract_error(wrong_size) == (
        "AutoData loader must use literal required_rows=1000"
    )

    missing_objective = """
handoff = {"production_execution_id": "exe_123"}
production_execution_id = handoff["production_execution_id"]
load_autodata_campaign_datasets(
    [dataset_path],
    receipt_path=receipt_path,
    required_rows=1000,
    expected_execution_ids=[production_execution_id],
    judge_rubric=training_data_contract["judge_rubric"],
)
"""
    assert "training_objective" in (
        server_api_tools._autodata_method_contract_error(missing_objective) or ""
    )

    empty_execution_ids = """
load_autodata_campaign_datasets(
    [dataset_path],
    receipt_path=receipt_path,
    required_rows=1000,
    expected_execution_ids=[],
    judge_rubric=training_data_contract["judge_rubric"],
    training_objective="sft",
)
"""
    assert "exactly one production execution ID" in (
        server_api_tools._autodata_method_contract_error(empty_execution_ids) or ""
    )

    valid = """
run_id = os.environ["AAR_CURRENT_RUN_ID"]
team_dir = os.environ["TEAM_DIR"]
names = (
    "training-handoff.json",
    "autodata-training-data-contract.json",
    "dataset",
    "production_execution_id",
    "training-consumption.json",
)
handoff = {"production_execution_id": "exe_123"}
production_execution_id = handoff["production_execution_id"]
load_autodata_campaign_datasets(
    [dataset_path],
    receipt_path=receipt_path,
    required_rows=1000,
    expected_execution_ids=[production_execution_id],
    judge_rubric=training_data_contract["judge_rubric"],
    training_objective="sft",
)
"""
    assert server_api_tools._autodata_method_contract_error(valid) is None

    placeholder = valid.replace(
        'production_execution_id = handoff["production_execution_id"]',
        'production_execution_id = "production_placeholder"',
    )
    assert "placeholders" in (
        server_api_tools._autodata_method_contract_error(placeholder) or ""
    )

    swallowed = valid.replace(
        "load_autodata_campaign_datasets(",
        "try:\n    load_autodata_campaign_datasets(",
    ) + "\nexcept Exception:\n    items = fallback_rows\n"
    assert "may not be swallowed" in (
        server_api_tools._autodata_method_contract_error(swallowed) or ""
    )
