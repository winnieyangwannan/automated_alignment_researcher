"""Contracts for repairing approved decoupled proposals from older launchers."""

import json
import os
from unittest.mock import patch

import pytest

from aar.research_loop.tools import server_api_tools


def test_missing_approved_run_id_is_deterministic_and_repairable(tmp_path) -> None:
    scores = tmp_path / "scores"
    marker = scores / ".proposals" / "chain-one.json"
    marker.parent.mkdir(parents=True)
    payload = {
        "approved": True,
        "execution_ready": True,
        "idea_name": "method_one",
        "idea_uid": "chain-one",
        "code_hash": "a" * 64,
        "paper": {"title": "An approved proposal"},
        "ts": 123.5,
        "verdict": {"approved": True},
    }
    marker.write_text(json.dumps(payload))
    environment = {
        "AAR_NO_LOCAL_GPU": "true",
        "IDEA_UID": "chain-one",
        "IDEA_NAME": "chain-one",
        "SCORES_DIR": str(scores),
    }

    with (
        patch.dict(os.environ, environment, clear=False),
        patch.object(
            server_api_tools,
            "_method_code",
            return_value=("method source", "a" * 64),
        ),
        patch.object(
            server_api_tools,
            "_stamp_run_proposal",
            return_value=True,
        ) as stamp,
    ):
        candidate = server_api_tools._approved_proposal_run_id_candidate()
        assert json.loads(marker.read_text()) == payload

        repaired = server_api_tools._ensure_approved_proposal_run_id()

    assert repaired == candidate
    assert repaired.startswith("chain-one-method_one-")
    assert json.loads(marker.read_text())["run_id"] == repaired
    stamp.assert_called_once_with(repaired)


def test_decoupled_execution_signals_always_require_run_id() -> None:
    for name in (
        "AAR_NO_LOCAL_GPU",
        "AAR_AUTODATA",
        "AAR_REQUIRE_TRAIN_RECEIPT",
        "EVAL_VIA_WORKER",
    ):
        with patch.dict(os.environ, {name: "true"}, clear=True):
            assert server_api_tools._requires_explicit_proposal_run_id()


def test_existing_run_id_rejects_mismatched_stamp(tmp_path) -> None:
    scores = tmp_path / "scores"
    marker = scores / ".proposals" / "chain-one.json"
    runs = marker.parent / "runs"
    runs.mkdir(parents=True)
    payload = {
        "approved": True,
        "execution_ready": True,
        "idea_name": "method_one",
        "idea_uid": "chain-one",
        "code_hash": "a" * 64,
        "paper": {"title": "approved"},
        "run_id": "chain-one-method-one-1",
        "ts": 123.5,
        "verdict": {"approved": True},
    }
    marker.write_text(json.dumps(payload))
    (runs / f"{payload['run_id']}.json").write_text(
        json.dumps({**payload, "paper": {"title": "different"}})
    )
    environment = {
        "AAR_NO_LOCAL_GPU": "true",
        "IDEA_UID": "chain-one",
        "IDEA_NAME": "chain-one",
        "SCORES_DIR": str(scores),
    }
    with (
        patch.dict(os.environ, environment, clear=False),
        patch.object(
            server_api_tools,
            "_method_code",
            return_value=("method source", "a" * 64),
        ),
        pytest.raises(RuntimeError, match="not bound"),
    ):
        server_api_tools._approved_proposal_run_id_candidate()


def test_terminal_run_id_allows_method_drift_but_still_validates_stamp(
    tmp_path,
) -> None:
    scores = tmp_path / "scores"
    marker = scores / ".proposals" / "chain-one.json"
    runs = marker.parent / "runs"
    runs.mkdir(parents=True)
    payload = {
        "approved": True,
        "execution_ready": True,
        "idea_name": "method_one",
        "idea_uid": "chain-one",
        "code_hash": "a" * 64,
        "paper": {"title": "approved"},
        "run_id": "chain-one-method-one-1",
        "ts": 123.5,
        "verdict": {"approved": True},
    }
    marker.write_text(json.dumps(payload))
    (runs / f"{payload['run_id']}.json").write_text(json.dumps(payload))
    environment = {
        "AAR_NO_LOCAL_GPU": "true",
        "IDEA_UID": "chain-one",
        "IDEA_NAME": "chain-one",
        "SCORES_DIR": str(scores),
    }
    with (
        patch.dict(os.environ, environment, clear=False),
        patch.object(
            server_api_tools,
            "_method_code",
            return_value=("later method source", "b" * 64),
        ),
    ):
        with pytest.raises(RuntimeError, match="code no longer matches"):
            server_api_tools._approved_proposal_run_id_candidate()
        assert (
            server_api_tools._approved_proposal_run_id_candidate(
                allow_method_drift=True
            )
            == payload["run_id"]
        )

        stamp = json.loads((runs / f"{payload['run_id']}.json").read_text())
        stamp["paper"] = {"title": "tampered"}
        (runs / f"{payload['run_id']}.json").write_text(json.dumps(stamp))
        with pytest.raises(RuntimeError, match="not bound"):
            server_api_tools._approved_proposal_run_id_candidate(
                allow_method_drift=True
            )
