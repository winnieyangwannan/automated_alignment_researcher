from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aar.failure_feedback import FailureFeedbackError, build_failure_feedback
from aar.research_loop.agent import AutonomousAgentLoop, BaseAgent


class _StopChecker:
    elapsed_time = 1.0

    @staticmethod
    def check():
        return None

    @staticmethod
    def record_error() -> None:
        return None

    @staticmethod
    def record_success() -> None:
        return None


def _loop(tmp_path: Path, failure: FailureFeedbackError) -> AutonomousAgentLoop:
    loop = object.__new__(AutonomousAgentLoop)
    loop.run_id = "run-test"
    loop.idea_uid = "idea-test"
    loop.idea_name = "idea-test"
    loop.backend = "claude"
    loop.model = "test-model"
    loop.max_runtime_seconds = 60
    loop.max_iterations = 3
    loop.session_count = 0
    loop.local_mode = True
    loop.findings_sync = None
    loop.stop_checker = _StopChecker()
    loop.logs_dir = tmp_path / "logs"
    loop.logs_dir.mkdir()
    loop._run_session = AsyncMock(side_effect=failure)
    loop._successful_score_result_pairs = lambda: 0
    return loop


def test_permanent_typed_session_failure_stops_without_retry(tmp_path: Path) -> None:
    failure = build_failure_feedback(
        RuntimeError("raw provider body API_KEY=secret"),
        error_code="autodata_action_bridge_failed",
        stage="autodata_action",
        public_summary="trusted AutoData action bridge command failed",
    )
    loop = _loop(tmp_path, FailureFeedbackError(failure))

    result = asyncio.run(loop.run())

    assert loop._run_session.await_count == 1
    assert result["stop_reason"] == "permanent_session_failure"
    assert result["last_failure"]["error_code"] == "autodata_action_bridge_failed"
    assert "raw provider body" not in str(result)
    assert "secret" not in str(result)


def test_only_explicit_retryable_session_failure_retries(tmp_path: Path) -> None:
    failure = build_failure_feedback(
        TimeoutError("private transport detail"),
        error_code="kimi_model_overloaded",
        stage="research_session",
        retryable=True,
        public_summary="Kimi model service is overloaded",
    )
    loop = _loop(tmp_path, FailureFeedbackError(failure))
    loop.max_iterations = 2
    loop._run_session = AsyncMock(
        side_effect=[FailureFeedbackError(failure), None]
    )

    with patch("aar.research_loop.agent.asyncio.sleep", new=AsyncMock()) as sleep:
        result = asyncio.run(loop.run())

    assert loop._run_session.await_count == 2
    sleep.assert_awaited_once()
    assert result["failed_sessions"] == 1
    assert result["successful_sessions"] == 1


def test_continuation_exhaustion_advances_without_backoff(tmp_path: Path) -> None:
    failure = build_failure_feedback(
        RuntimeError("private conversation"),
        error_code="required_completion_missing",
        stage="research_session",
        retryable=True,
        disposition="advance_session",
        public_summary="continuation budget exhausted",
    )
    loop = _loop(tmp_path, FailureFeedbackError(failure))
    loop.max_iterations = 2
    loop._run_session = AsyncMock(
        side_effect=[FailureFeedbackError(failure), None]
    )

    with patch("aar.research_loop.agent.asyncio.sleep", new=AsyncMock()) as sleep:
        result = asyncio.run(loop.run())

    assert loop._run_session.await_count == 2
    sleep.assert_not_awaited()
    assert result["failed_sessions"] == 1
    assert result["successful_sessions"] == 1


def test_one_session_canary_does_not_exceed_ceiling_after_exhaustion(
    tmp_path: Path,
) -> None:
    failure = build_failure_feedback(
        RuntimeError("private conversation"),
        error_code="required_completion_missing",
        stage="research_session",
        retryable=True,
        disposition="advance_session",
        public_summary="continuation budget exhausted",
    )
    loop = _loop(tmp_path, FailureFeedbackError(failure))
    loop.max_iterations = 1

    with patch("aar.research_loop.agent.asyncio.sleep", new=AsyncMock()) as sleep:
        result = asyncio.run(loop.run())

    assert loop._run_session.await_count == 1
    sleep.assert_not_awaited()
    assert result["sessions"] == 1
    assert result["stop_reason"] == "max_iterations"


def test_run_bound_candidate_failure_advances_without_operation_retry(
    tmp_path: Path,
) -> None:
    failure = build_failure_feedback(
        RuntimeError("candidate method failed preflight"),
        error_code="training_python_exception",
        stage="training",
        retryable=False,
        public_summary="candidate training failed",
    )
    failure["run_id"] = "candidate-run-1"
    loop = _loop(tmp_path, FailureFeedbackError(failure))
    loop.max_iterations = 2
    loop._run_session = AsyncMock(
        side_effect=[FailureFeedbackError(failure), None]
    )

    with patch("aar.research_loop.agent.asyncio.sleep", new=AsyncMock()) as sleep:
        result = asyncio.run(loop.run())

    assert loop._run_session.await_count == 2
    sleep.assert_not_awaited()
    assert result["failed_sessions"] == 1
    assert result["successful_sessions"] == 1
    assert result["stop_reason"] == "max_iterations"


def test_malformed_failure_feedback_fails_closed_without_leaking(
    tmp_path: Path,
) -> None:
    failure = FailureFeedbackError(
        {
            "schema": "not-a-valid-schema",
            "status": "failed",
            "stage": "training",
            "error_code": "training_python_exception",
            "retryable": True,
            "run_id": "candidate-run-1",
            "secret": "API_KEY=do-not-return-this",
        }
    )
    loop = _loop(tmp_path, failure)

    with patch("aar.research_loop.agent.asyncio.sleep", new=AsyncMock()) as sleep:
        result = asyncio.run(loop.run())

    assert loop._run_session.await_count == 1
    sleep.assert_not_awaited()
    assert result["stop_reason"] == "permanent_session_failure"
    assert result["last_failure"]["error_code"] == "invalid_failure_feedback"
    assert "do-not-return-this" not in str(result)
    assert "secret" not in result["last_failure"]


def test_base_agent_returns_typed_failure_and_hides_backend_detail(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEAM_DIR", str(tmp_path))
    agent = object.__new__(BaseAgent)
    agent.name = "test-agent"
    agent._execute_once = AsyncMock(
        side_effect=RuntimeError("provider body API_KEY=secret heldout-row-17")
    )

    result = asyncio.run(agent.execute("task"))

    assert result.success is False
    assert result.error == "Claude research session failed"
    assert result.failure is not None
    assert result.failure["error_code"] == "claude_agent_failed"
    assert result.failure["retryable"] is False
    assert "heldout-row-17" not in str(result)
    assert "evidence" not in result.failure
    assert not (tmp_path / "secrets").exists()


def test_claude_system_heartbeats_do_not_prevent_progress_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEAM_DIR", str(tmp_path))
    closed = False

    class SystemMessage:
        pass

    class HeartbeatOnlyClient:
        def __init__(self, *, options) -> None:
            self.options = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            nonlocal closed
            closed = True

        async def query(self, _task: str) -> None:
            return None

        async def receive_response(self):
            while True:
                await asyncio.sleep(0.01)
                yield SystemMessage()

    agent = BaseAgent(
        name="heartbeat-only",
        allowed_tools=[],
        workspace=tmp_path,
        mcp_servers={},
        progress_timeout_seconds=0.05,
    )
    with patch(
        "aar.research_loop.agent.ClaudeSDKClient", HeartbeatOnlyClient
    ):
        result = asyncio.run(agent.execute("task"))

    assert result.success is False
    assert result.error == (
        "Claude research session stopped after no substantive progress"
    )
    assert result.failure is not None
    assert result.failure["error_code"] == "claude_progress_timeout"
    assert result.failure["retryable"] is False
    assert closed is True
