"""Bounded, secret-safe failure feedback with digest-bound evidence pointers."""

from __future__ import annotations

import re
from typing import Any

SCHEMA = "aar.failure-feedback/v1"

_BEARER = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|authorization|cookie|password|secret|token)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_URL_CREDENTIALS = re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@")
_URL_QUERY = re.compile(r"(?i)(https?://[^\s?]+)\?[^\s]+")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\n]*PRIVATE KEY-----.*?-----END [^-\n]*PRIVATE KEY-----",
    re.DOTALL,
)
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_STAGE = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_EXCEPTION_TYPE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,127}\Z")


class FailureFeedbackError(RuntimeError):
    """Exception carrying a research-safe structured failure payload."""

    def __init__(self, feedback: dict[str, Any]) -> None:
        self.feedback = feedback
        super().__init__(str(feedback.get("summary") or feedback.get("error_code")))


def sanitize_failure_summary(value: object, *, limit: int = 1000) -> str:
    """Return one bounded diagnostic line without common credential forms."""

    if limit < 32:
        raise ValueError("failure summary limit must be at least 32")
    text = " ".join(str(value).split())
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", text)
    text = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", text)
    text = _URL_QUERY.sub(r"\1?[REDACTED]", text)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_failure_feedback(
    error: BaseException | object,
    *,
    error_code: str,
    stage: str,
    retryable: bool = False,
    public_summary: object | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    """Build a stable handoff for callers that must not return raw exceptions.

    Credential redaction does not make held-out examples or prompt text public.
    Boundaries crossing an evaluation-isolation domain must supply an already
    non-content-bearing ``public_summary``.
    """

    if _ERROR_CODE.fullmatch(error_code) is None:
        raise ValueError("error_code must be a lowercase identifier")
    if _STAGE.fullmatch(stage) is None:
        raise ValueError("stage must be a lowercase identifier")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "failed",
        "stage": stage,
        "error_code": error_code,
        "retryable": bool(retryable),
        "exception_type": type(error).__name__,
        "summary": sanitize_failure_summary(
            error if public_summary is None else public_summary,
            limit=limit,
        ),
    }
    return result


def feedback_from_exception(
    error: BaseException,
    *,
    error_code: str,
    stage: str,
    retryable: bool = False,
    public_summary: object,
) -> dict[str, Any]:
    """Preserve existing typed feedback or create a static-summary fallback."""

    if isinstance(error, FailureFeedbackError):
        return dict(error.feedback)
    return build_failure_feedback(
        error,
        error_code=error_code,
        stage=stage,
        retryable=retryable,
        public_summary=public_summary,
    )


def safe_failure_feedback_view(
    value: object,
    *,
    public_summary: str | None = None,
) -> dict[str, Any] | None:
    """Validate a stored feedback object and discard all free-form fields."""

    if not isinstance(value, dict):
        return None
    stage = value.get("stage")
    error_code = value.get("error_code")
    retryable = value.get("retryable")
    if (
        value.get("schema") != SCHEMA
        or value.get("status") != "failed"
        or not isinstance(stage, str)
        or _STAGE.fullmatch(stage) is None
        or not isinstance(error_code, str)
        or _ERROR_CODE.fullmatch(error_code) is None
        or not isinstance(retryable, bool)
    ):
        return None
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "failed",
        "stage": stage,
        "error_code": error_code,
        "retryable": retryable,
        "summary": sanitize_failure_summary(
            public_summary or f"{stage} failed ({error_code})"
        ),
    }
    exception_type = value.get("exception_type")
    if isinstance(exception_type, str) and _EXCEPTION_TYPE.fullmatch(exception_type):
        result["exception_type"] = exception_type
    for key in ("exit_code", "count"):
        field = value.get(key)
        if isinstance(field, int) and not isinstance(field, bool):
            result[key] = field
    run_id = value.get("run_id")
    if isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,256}", run_id):
        result["run_id"] = run_id
    return result
