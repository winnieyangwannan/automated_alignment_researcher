from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from aar.failure_feedback import FailureFeedbackError, build_failure_feedback
from aar.research_loop.tools.kimi_mcp_server import _mcp_failure
from aar.research_loop.tools.server_api_tools import _tool_failure


def test_tool_failure_returns_static_feedback_without_raw_evidence(
    tmp_path: Path,
) -> None:
    with patch.dict("os.environ", {"TEAM_DIR": str(tmp_path)}, clear=False):
        result = _tool_failure(
            RuntimeError("prompt row 12; API_KEY=must-not-leak"),
            error_code="autodata_review_failed",
            stage="autodata_approval",
            public_summary="AutoData approval review failed",
        )

    public = json.dumps(result)
    assert result["error"] == "AutoData approval review failed"
    assert result["failure"]["error_code"] == "autodata_review_failed"
    assert "prompt row 12" not in public
    assert "must-not-leak" not in public
    assert "evidence" not in result["failure"]


def test_tool_failure_preserves_typed_nested_failure(tmp_path: Path) -> None:
    feedback = build_failure_feedback(
        RuntimeError("private stderr"),
        error_code="autodata_bootstrap_cli_failed",
        stage="autodata_bootstrap",
        public_summary="AutoData bootstrap command failed",
    )

    with patch.dict("os.environ", {"TEAM_DIR": str(tmp_path)}, clear=False):
        result = _tool_failure(
            FailureFeedbackError(feedback),
            error_code="autodata_bootstrap_failed",
            stage="autodata_bootstrap",
            public_summary="AutoData workspace bootstrap failed",
        )

    assert result["failure"]["error_code"] == feedback["error_code"]
    assert result["failure"]["summary"] == feedback["summary"]
    assert result["error"] == "AutoData bootstrap command failed"


def test_unexpected_mcp_failure_does_not_echo_tool_exception() -> None:
    feedback = _mcp_failure(
        RuntimeError("private prompt row; API_KEY=must-not-cross-boundary")
    )

    assert feedback["error_code"] == "mcp_tool_failed"
    assert feedback["summary"] == "research tool failed"
    assert "private prompt" not in str(feedback)
    assert "must-not-cross-boundary" not in str(feedback)
