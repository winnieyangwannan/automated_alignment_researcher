from __future__ import annotations

from aar.failure_feedback import (
    FailureFeedbackError,
    build_failure_feedback,
    feedback_from_exception,
    safe_failure_feedback_view,
    sanitize_failure_summary,
)


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
    assert "held-out prompt" not in str(view)
    assert "evidence" not in view
