"""Regression coverage for one-shot approved-proposal recovery."""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aar.research_loop.kimi_agent import KimiAgent, OrchestrationIncident


def test_approved_proposal_recovery_disables_after_finding_persists(
    tmp_path,
) -> None:
    run_id = "chain-candidate-1"
    environment = {
        "AAR_RESUME_APPROVED_PROPOSAL": "1",
        "TEAM_DIR": str(tmp_path),
    }
    with (
        patch.dict(os.environ, environment, clear=False),
        patch.object(KimiAgent, "_approved_run_id", return_value=run_id),
    ):
        assert KimiAgent._resume_approved_proposal_enabled()

        registry = (
            tmp_path / ".finding_dedup" / f"runid_{run_id}" / "post.json"
        )
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"finding_id": "finding-1"}))

        assert not KimiAgent._resume_approved_proposal_enabled()


def test_approved_proposal_without_run_id_stops_as_infrastructure_incident(
    tmp_path,
) -> None:
    method = tmp_path / "aar" / "ideas" / "candidate" / "run.py"
    method.parent.mkdir(parents=True)
    method.write_text("def run():\n    return None\n")
    agent = KimiAgent(
        "test-agent",
        tmp_path,
        cli_path="/bin/true",
        completion_tool="share_finding",
    )
    output = {
        "tool_uses": [
            {
                "tool": "submit_idea_proposal",
                "input": {"idea_name": "candidate"},
            }
        ]
    }
    with (
        patch.object(agent, "_approved_run_id", return_value=None),
        patch.object(agent, "_proposal_is_approved", return_value=True),
        patch.object(
            agent,
            "_proposal_marker_changed_this_session",
            return_value=True,
        ),
        patch.object(agent, "_raise_orchestration_incident") as fail_stop,
    ):
        fail_stop.side_effect = OrchestrationIncident("missing run id")
        with pytest.raises(OrchestrationIncident, match="missing run id"):
            agent._continuation_prompt(output)

    fail_stop.assert_called_once()


def test_native_resume_submits_and_waits_before_first_model_turn() -> None:
    run_id = "approved-run-1"
    agent = KimiAgent(
        "test-agent",
        Path.cwd(),
        cli_path="/bin/true",
        completion_tool="share_finding",
    )
    submit = Mock()
    wait_for_score = AsyncMock(side_effect=RuntimeError("stop after host wait"))
    run_command = AsyncMock()
    with (
        patch.dict(
            os.environ,
            {
                "AAR_AUTODATA": "0",
                "AAR_RESUME_APPROVED_PROPOSAL": "1",
            },
            clear=False,
        ),
        patch.object(
            agent, "_resume_approved_proposal_enabled", return_value=True
        ),
        patch.object(agent, "_approved_run_id", return_value=run_id),
        patch.object(
            agent, "_ensure_approved_training_submission", new=submit
        ),
        patch.object(agent, "_wait_for_training_result", new=wait_for_score),
        patch.object(agent, "_run_command", new=run_command),
    ):
        result = asyncio.run(agent.execute("resume the approved proposal"))

    assert not result.success
    assert "stop after host wait" in (result.error or "")
    submit.assert_called_once_with()
    wait_for_score.assert_awaited_once_with()
    run_command.assert_not_awaited()


def test_native_resume_without_bound_run_id_stops_before_model_turn() -> None:
    agent = KimiAgent(
        "test-agent",
        Path.cwd(),
        cli_path="/bin/true",
        completion_tool="share_finding",
    )
    run_command = AsyncMock()
    with (
        patch.dict(
            os.environ,
            {
                "AAR_AUTODATA": "0",
                "AAR_RESUME_APPROVED_PROPOSAL": "1",
            },
            clear=False,
        ),
        patch.object(
            agent, "_resume_approved_proposal_enabled", return_value=True
        ),
        patch.object(agent, "_approved_run_id", return_value=None),
        patch.object(agent, "_run_command", new=run_command),
        patch.object(agent, "_publish_orchestration_incident"),
    ):
        with pytest.raises(OrchestrationIncident, match="no fully bound trusted"):
            asyncio.run(agent.execute("resume the approved proposal"))

    run_command.assert_not_awaited()


@pytest.mark.parametrize("downstream_artifact", ["score", "adapter_submission"])
def test_training_submission_is_idempotent_without_receipt_when_downstream_exists(
    tmp_path, downstream_artifact
) -> None:
    run_id = "chain-approved-run"
    scores = tmp_path / "scores"
    team = tmp_path / "team"
    scores.mkdir()
    if downstream_artifact == "score":
        (scores / f"{run_id}.json").write_text('{"score": 1}\n')
    else:
        submitted = team / "submissions" / run_id / ".submitted"
        submitted.parent.mkdir(parents=True)
        submitted.write_text("done\n")
    agent = KimiAgent(
        "test-agent",
        tmp_path,
        cli_path="/bin/true",
        completion_tool="share_finding",
    )
    submit = Mock()
    with (
        patch.dict(
            os.environ,
            {
                "AAR_REQUIRE_TRAIN_RECEIPT": "1",
                "SCORES_DIR": str(scores),
                "TEAM_DIR": str(team),
            },
            clear=False,
        ),
        patch.object(agent, "_approved_run_id", return_value=run_id),
        patch.object(agent, "active_orchestration_incident", return_value=None),
        patch("aar.research_loop.kimi_agent.subprocess.run", new=submit),
    ):
        agent._ensure_approved_training_submission()

    submit.assert_not_called()


def test_native_resume_context_forbids_reproposal() -> None:
    run_id = "approved-run-1"
    agent = KimiAgent(
        "test-agent",
        Path.cwd(),
        cli_path="/bin/true",
        completion_tool="share_finding",
    )
    with (
        patch.dict(os.environ, {"AAR_AUTODATA": "0"}, clear=False),
        patch.object(
            agent, "_resume_approved_proposal_enabled", return_value=True
        ),
        patch.object(agent, "_approved_run_id", return_value=run_id),
    ):
        task = agent._with_resumable_approved_run("original task")

    assert "AUTOMATIC RESUME CONTEXT" in task
    assert run_id in task
    assert "Do not restart literature" in task
    assert "share_finding" in task


def test_explicit_proposal_run_id_wins_over_same_code_legacy_stamp(
    tmp_path,
) -> None:
    scores = tmp_path / "scores"
    runs = scores / ".proposals" / "runs"
    runs.mkdir(parents=True)
    marker = {
        "approved": True,
        "idea_name": "candidate",
        "code_hash": "a" * 64,
        "paper": {"title": "current"},
        "run_id": "chain-current",
    }
    (scores / ".proposals" / "chain.json").write_text(json.dumps(marker))
    (runs / "chain-current.json").write_text(
        json.dumps({**marker, "stamped_ts": 1})
    )
    (runs / "chain-newer.json").write_text(
        json.dumps(
            {
                **marker,
                "run_id": "chain-newer",
                "paper": {"title": "wrong"},
                "stamped_ts": 999,
            }
        )
    )

    with patch.dict(
        os.environ,
        {"SCORES_DIR": str(scores), "IDEA_UID": "chain"},
        clear=False,
    ):
        assert KimiAgent._approved_run_id() == "chain-current"


def test_explicit_proposal_run_id_rejects_mismatched_stamp(tmp_path) -> None:
    scores = tmp_path / "scores"
    runs = scores / ".proposals" / "runs"
    runs.mkdir(parents=True)
    marker = {
        "approved": True,
        "idea_name": "candidate",
        "code_hash": "a" * 64,
        "paper": {"title": "current"},
        "run_id": "chain-current",
    }
    (scores / ".proposals" / "chain.json").write_text(json.dumps(marker))
    (runs / "chain-current.json").write_text(
        json.dumps({**marker, "paper": {"title": "different"}})
    )

    with patch.dict(
        os.environ,
        {"SCORES_DIR": str(scores), "IDEA_UID": "chain"},
        clear=False,
    ):
        assert KimiAgent._approved_run_id() is None
