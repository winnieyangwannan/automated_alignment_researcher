from __future__ import annotations

import ast
from pathlib import Path

from aar.failure_feedback import (
    FailureFeedbackError,
    build_failure_feedback,
    failure_guidance,
    feedback_from_exception,
    has_actionable_failure_guidance,
    safe_failure_feedback_view,
    sanitize_failure_summary,
)


def _production_literal_error_codes() -> set[str]:
    root = Path(__file__).resolve().parents[1]
    paths = [
        *sorted((root / "aar").rglob("*.py")),
        *sorted((root / "scripts").glob("*.py")),
        root / "run.py",
    ]
    result: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "error_code"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    result.add(keyword.value.value)
    return result


def test_every_production_failure_stage_has_static_safe_guidance() -> None:
    stages = {
        "research_session",
        "research_tool",
        "proposal_review",
        "proposal_submission",
        "training_submission",
        "training",
        "evaluation_submission",
        "evaluation",
        "evaluation_scoring",
        "result_publication",
        "autodata_bootstrap",
        "autodata_approval",
        "autodata_action",
        "autodata_grounding",
        "autodata_lifecycle",
        "autodata_production",
        "autodata_handoff",
    }

    for stage in stages:
        guidance = failure_guidance(stage, "representative_failure")
        assert guidance
        assert guidance != (
            "Use the typed stage and error code to repair the failed operation."
        )


def test_every_literal_production_error_code_has_actionable_guidance() -> None:
    codes = _production_literal_error_codes()

    missing = sorted(code for code in codes if not has_actionable_failure_guidance(code))

    assert codes
    assert missing == []


def test_training_interface_failures_have_specific_guidance() -> None:
    dataset_guidance = failure_guidance(
        "training", "training_dataset_interface_invalid"
    )
    config_guidance = failure_guidance(
        "training", "training_method_config_invalid"
    )

    assert "datasets.Dataset" in dataset_guidance
    assert "train_dataset" in dataset_guidance
    assert "dry_run" in config_guidance
    assert "smoke_run" in config_guidance


def test_failure_summary_is_bounded_and_redacts_common_secret_forms() -> None:
    raw = (
        "request failed Authorization: Bearer-secret token=abc123 "
        "Bearer xyz987 https://user:pass@example.test/v1?api_key=hidden "
        + "x" * 1000
    )
    summary = sanitize_failure_summary(raw, limit=200)

    assert len(summary) == 200
    assert "abc123" not in summary
    assert "xyz987" not in summary
    assert "user:pass" not in summary
    assert "api_key=hidden" not in summary
    assert "[REDACTED]" in summary


def test_structured_feedback_keeps_only_safe_cause() -> None:
    feedback = build_failure_feedback(
        RuntimeError("provider returned HTTP 409; token=secret"),
        error_code="provider_rejected",
        stage="production",
    )

    assert feedback["summary"] == (
        "provider returned HTTP 409; token=[REDACTED]"
    )
    assert feedback["retryable"] is False
    assert feedback["disposition"] == "halt"
    assert feedback["guidance"]
    assert "evidence" not in feedback


def test_public_summary_prevents_cross_boundary_content_leak() -> None:
    feedback = build_failure_feedback(
        RuntimeError("held-out row text API_KEY=secret"),
        error_code="evaluation_scoring_failure",
        stage="evaluation_scoring",
        public_summary="evaluation scoring failed; inspect evaluator-private logs",
    )

    assert feedback["exception_type"] == "RuntimeError"
    assert feedback["summary"] == (
        "evaluation scoring failed; inspect evaluator-private logs"
    )
    assert "held-out" not in str(feedback)
    assert "secret" not in str(feedback)


def test_typed_feedback_is_preserved() -> None:
    original = build_failure_feedback(
        RuntimeError("private"),
        error_code="native_cli_failed",
        stage="autodata_lifecycle",
        public_summary="native AutoData command failed",
    )
    recovered = feedback_from_exception(
        FailureFeedbackError(original),
        error_code="fallback",
        stage="fallback",
        public_summary="fallback",
    )
    assert recovered == original


def test_safe_view_drops_stored_summary_and_invalid_pointer() -> None:
    view = safe_failure_feedback_view(
        {
            "schema": "aar.failure-feedback/v1",
            "status": "failed",
            "stage": "training",
            "error_code": "training_failed",
            "retryable": False,
            "summary": "held-out prompt row",
            "evidence": {
                "relative_path": "../../secret",
                "sha256": "sha256:" + "a" * 64,
                "size_bytes": 10,
            },
        }
    )

    assert view is not None
    assert view["summary"] == "training failed (training_failed)"
    assert view["disposition"] == "halt"
    assert view["guidance"]
    assert "held-out prompt" not in str(view)
    assert "evidence" not in view


def test_advance_session_disposition_survives_safe_view() -> None:
    feedback = build_failure_feedback(
        RuntimeError("private conversational state"),
        error_code="required_completion_missing",
        stage="research_session",
        retryable=True,
        disposition="advance_session",
        public_summary="continuation budget exhausted",
    )

    view = safe_failure_feedback_view(feedback)

    assert view is not None
    assert view["retryable"] is True
    assert view["disposition"] == "advance_session"
    assert "fresh research session" in view["guidance"]
