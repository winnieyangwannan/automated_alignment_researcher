"""Protected HTTP transport and usage provenance adapted from recipe v2.

This module contains no generation strategy or scoring policy.
"""

from __future__ import annotations

import email.utils
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


_REQUEST_TELEMETRY: dict[str, int] = {}
_BRITTLE_FORMAT_PATTERNS = (
    (
        "exact word count",
        re.compile(
            r"(?:\b(?:write|draft|produce|provide|return|respond|answer|summarize|"
            r"limit|keep|use)\b[^.!?\n]{0,48}\b(?:exactly\s+)?"
            r"\d{1,5}(?:[- ]words?|\s+words?)\b)|"
            r"(?:\b(?:response|answer|summary|draft|output)\b[^.!?\n]{0,32}"
            r"\b(?:must|should|needs?\s+to)\b[^.!?\n]{0,24}"
            r"\b(?:exactly\s+)?\d{1,5}\s+words?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "exact item count",
        re.compile(
            r"(?:\b(?:use|provide|return|write|draft|format)\b[^.!?\n]{0,48}"
            r"\b(?:exactly\s+)?"
            r"(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(?:bullets?|bullet points?|sentences?|paragraphs?)\b)|"
            r"(?:\b(?:response|answer|summary|draft|output)\b[^.!?\n]{0,32}"
            r"\b(?:must|should|needs?\s+to)\b[^.!?\n]{0,24}"
            r"\b(?:contain|have|use|be)?\s*(?:exactly\s+)?"
            r"(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(?:bullets?|bullet points?|sentences?|paragraphs?)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "no-extra-text constraint",
        re.compile(
            r"(?:\b(?:return|provide|write|respond|answer|output|give)\b"
            r"[^.!?\n]{0,48}\bno\s+(?:additional|extra|other)\s+"
            r"(?:text|commentary|explanation|content)\b)|"
            r"(?:^\s*no\s+(?:additional|extra|other)\s+"
            r"(?:text|commentary|explanation|content)\b)|"
            r"\bdo not include (?:anything|any text) else\b",
            re.IGNORECASE,
        ),
    ),
)

_TARGET_ENV = (
    "AUTODATA_TARGET_URL",
    "AUTODATA_TARGET_MODEL",
    "AUTODATA_TARGET_DEPLOYMENT_ID",
    "AUTODATA_TARGET_CHECKPOINT_HASH",
)


def _reset_request_telemetry() -> None:
    _REQUEST_TELEMETRY.clear()


def _increment_request_telemetry(role: str, signal: str) -> None:
    key = f"telemetry_{role}_{signal}"
    _REQUEST_TELEMETRY[key] = _REQUEST_TELEMETRY.get(key, 0) + 1


def _operational_metrics(
    provider_usage: list[dict[str, Any]],
) -> dict[str, float]:
    result = {key: float(value) for key, value in _REQUEST_TELEMETRY.items()}
    for role in ("generator", "target", "judge"):
        result[f"telemetry_{role}_completed_calls"] = float(
            sum(entry.get("role") == role for entry in provider_usage)
        )
    return result


class MeteredCallError(RuntimeError):
    """A provider answered and incurred usage, but its content was unusable."""

    def __init__(
        self,
        message: str,
        usage: dict[str, Any] | list[dict[str, Any]],
        *,
        reason_code: str | None = None,
    ) -> None:
        super().__init__(message)
        usages = [usage] if isinstance(usage, dict) else list(usage)
        if not usages:
            raise ValueError("metered call errors require provider usage")
        self.usages = tuple(usages)
        self.usage = usages[-1]
        self.reason_code = reason_code


class JudgeContractError(RuntimeError):
    """A bounded, content-free explanation of a judge wire-contract failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RecipeTaskError(RuntimeError):
    """A deterministic recipe rejection with a safe result reason code."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


_FAILURE_BEARER = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_FAILURE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|authorization|cookie|password|secret|token)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_FAILURE_URL_CREDENTIALS = re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@")
_FAILURE_URL_QUERY = re.compile(r"(?i)(https?://[^\s?]+)\?[^\s]+")
_FAILURE_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-\n]*PRIVATE KEY-----.*?-----END [^-\n]*PRIVATE KEY-----",
    re.DOTALL,
)


def _safe_failure_detail(error: BaseException, *, limit: int = 800) -> str:
    """Keep an actionable native task error without copying secrets or bodies."""

    parts = [f"{type(error).__name__}: {error}"]
    cause = error.__cause__
    if cause is not None and str(cause):
        parts.append(f"caused by {type(cause).__name__}: {cause}")
    text = " ".join("; ".join(parts).split())
    text = _FAILURE_PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _FAILURE_BEARER.sub("Bearer [REDACTED]", text)
    text = _FAILURE_SECRET.sub(r"\1\2[REDACTED]", text)
    text = _FAILURE_URL_CREDENTIALS.sub(r"\1[REDACTED]@", text)
    text = _FAILURE_URL_QUERY.sub(r"\1?[REDACTED]", text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _failure_reason_code(error: BaseException) -> str:
    explicit = getattr(error, "reason_code", None)
    if isinstance(explicit, str) and re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", explicit):
        return explicit
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__
    for item in chain:
        if isinstance(item, urllib.error.HTTPError):
            return f"provider_http_{item.code}"
        if isinstance(item, urllib.error.URLError):
            if isinstance(item.reason, TimeoutError):
                return "provider_timeout"
            return "provider_connection_failure"
    if any(isinstance(item, TimeoutError) for item in chain):
        return "provider_timeout"
    if any(isinstance(item, ConnectionError) for item in chain):
        return "provider_connection_failure"
    if any(isinstance(item, json.JSONDecodeError) for item in chain):
        return "provider_invalid_json"
    if isinstance(error, MeteredCallError):
        role = str(error).split(maxsplit=1)[0].lower()
        if role in {"generator", "target", "judge"}:
            return f"{role}_invalid_content"
    if "required runtime setting" in str(error):
        return "recipe_configuration_error"
    return "model_or_parse_failure"


def _generator_content_reason_code(error: BaseException) -> str:
    """Classify unusable generator output without retaining model content."""
    detail = str(error).lower()
    if "no output text" in detail:
        return "generator_missing_output"
    if isinstance(error, json.JSONDecodeError) or any(
        marker in detail
        for marker in (
            "did not contain a json object",
            "output json is not an object",
        )
    ):
        return "generator_invalid_json"
    if "structured generation requires" in detail:
        return "generator_missing_fields"
    if "requires a non-empty" in detail:
        return "generator_empty_field"
    if "exceeded the recipe size limit" in detail:
        return "generator_size_limit"
    return "generator_invalid_content"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required runtime setting is missing: {name}")
    return value


def _bounded_positive_int_env(name: str, default: str, *, maximum: int) -> int:
    raw = os.environ.get(name, default).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if value < 1 or value > maximum or str(value) != raw:
        raise RuntimeError(f"{name} must be an integer from 1 through {maximum}")
    return value


def _brittle_format_constraint(
    task_request: str, pressure_frame: str | None = None
) -> str | None:
    """Reject imperative format traps only in mutable wrapper components."""
    for component, text in (
        ("task_request", task_request),
        ("pressure_frame", pressure_frame),
    ):
        if not isinstance(text, str):
            continue
        for label, pattern in _BRITTLE_FORMAT_PATTERNS:
            match = pattern.search(text)
            if match:
                return f"{component} {label}: {match.group(0)!r}"
    return None


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    role: str,
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, sort_keys=True).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    last: Exception | None = None
    attempts = _bounded_positive_int_env(
        "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS", "3", maximum=5
    )
    for attempt in range(attempts):
        _increment_request_telemetry(role, "request_attempts")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.load(response)
            if not isinstance(value, dict):
                raise RuntimeError("model endpoint returned a non-object response")
            return value
        except (OSError, ValueError, urllib.error.HTTPError) as error:
            last = error
            _increment_request_telemetry(role, "request_failures")
            message = str(error).lower()
            if (
                (isinstance(error, urllib.error.HTTPError) and error.code == 429)
                or "429" in message
                or "rate limit" in message
            ):
                _increment_request_telemetry(role, "http_429_or_rate_limit")
            if (
                isinstance(error, TimeoutError)
                or "timeout" in message
                or "timed out" in message
            ):
                _increment_request_telemetry(role, "timeouts")
            if isinstance(error, ConnectionResetError) or "reset" in message:
                _increment_request_telemetry(role, "connection_resets")
            retryable = isinstance(error, urllib.error.HTTPError) and error.code in {
                429,
                500,
                502,
                503,
                504,
            }
            if not retryable or attempt == attempts - 1:
                break
            retry_after = 0.0
            raw_retry_after = (
                error.headers.get("Retry-After") if error.headers else None
            )
            if raw_retry_after:
                try:
                    retry_after = max(0.0, float(raw_retry_after))
                except ValueError:
                    try:
                        parsed = email.utils.parsedate_to_datetime(raw_retry_after)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        retry_after = max(
                            0.0, (parsed - datetime.now(timezone.utc)).total_seconds()
                        )
                    except (TypeError, ValueError, OverflowError):
                        retry_after = 0.0
            delay = min(60.0, float(2**attempt))
            time.sleep(min(60.0, max(retry_after, delay)))
    raise RuntimeError(
        f"model request failed after {attempts} bounded attempts: {last}"
    ) from last


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    try:
        value = json.loads(stripped)
    except ValueError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("model output did not contain a JSON object")
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("model output JSON is not an object")
    return value


def _usage(
    response: dict[str, Any],
    *,
    role: str,
    model: str,
    input_rate: Decimal,
    output_rate: Decimal,
    max_input_tokens: int,
    max_output_tokens: int,
    deployment_id: str | None = None,
    checkpoint_hash: str | None = None,
) -> dict[str, Any]:
    raw = response.get("usage")
    if not isinstance(raw, dict):
        raise RuntimeError(f"{role} response omitted usage")
    input_tokens = raw.get("prompt_tokens", raw.get("input_tokens"))
    output_tokens = raw.get("completion_tokens", raw.get("output_tokens"))
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens < 0
    ):
        raise RuntimeError(f"{role} response contained invalid token usage")
    cost = (
        Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
    ) / Decimal(1_000_000)
    request_id = response.get("id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise RuntimeError(f"{role} response omitted provider request id")
    usage = {
        "request_id": request_id.strip(),
        "role": role,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": format(cost, "f"),
        "cost_basis": "operator-configured-token-rates",
    }
    if deployment_id is not None:
        usage["deployment_id"] = deployment_id
    if checkpoint_hash is not None:
        usage["checkpoint_hash"] = checkpoint_hash
    if input_tokens > max_input_tokens or output_tokens > max_output_tokens:
        raise MeteredCallError(
            f"{role} usage exceeded the operator-pinned token ceiling", usage
        )
    return usage


def _validate_provider_usage(
    provider_usage: list[dict[str, Any]],
    *,
    target_config: dict[str, str] | None,
) -> None:
    """Fail the task before baseline review when provenance is incomplete."""

    roles = {
        role: [entry for entry in provider_usage if entry.get("role") == role]
        for role in ("generator", "target", "judge")
    }
    required_roles = ("generator", "judge") + (
        ("target",) if target_config is not None else ()
    )
    if any(not roles[role] for role in required_roles):
        raise RuntimeError("provider usage is missing a required role")
    if target_config is None and roles["target"]:
        raise RuntimeError("provider usage recorded an unexpected target role")
    required_identity = ("request_id", "model")
    if any(
        not isinstance(entry.get(key), str) or not entry[key].strip()
        for entries in roles.values()
        for entry in entries
        for key in required_identity
    ):
        raise RuntimeError("provider usage contains incomplete provider identity")
    request_ids = [
        entry["request_id"] for entries in roles.values() for entry in entries
    ]
    if len(request_ids) != len(set(request_ids)):
        raise RuntimeError("provider usage contains duplicate request ids")

    generator_identity = (
        _required_env("AUTODATA_GENERATOR_MODEL"),
        _required_env("AUTODATA_GENERATOR_DEPLOYMENT_ID"),
    )
    if any(
        (entry["model"], entry.get("deployment_id")) != generator_identity
        for entry in roles["generator"]
    ):
        raise RuntimeError(
            "generator usage does not match the trusted runtime deployment"
        )
    if any(
        entry["model"] != _required_env("AUTODATA_JUDGE_MODEL")
        for entry in roles["judge"]
    ):
        raise RuntimeError("judge usage does not match the trusted runtime model")
    if target_config is not None:
        target_identity = (
            target_config["AUTODATA_TARGET_MODEL"],
            target_config["AUTODATA_TARGET_DEPLOYMENT_ID"],
            target_config["AUTODATA_TARGET_CHECKPOINT_HASH"],
        )
        if any(
            (
                entry["model"],
                entry.get("deployment_id"),
                entry.get("checkpoint_hash"),
            )
            != target_identity
            for entry in roles["target"]
        ):
            raise RuntimeError(
                "target usage does not match the trusted runtime checkpoint"
            )


def _generator_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
    return _responses_text(response, role="generator")


def _judge_text(response: dict[str, Any]) -> str:
    return _responses_text(response, role="judge")


def _responses_text(response: dict[str, Any], *, role: str) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    pieces: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                if isinstance(content.get("text"), str):
                    pieces.append(content["text"])
    if not pieces:
        raise RuntimeError(f"{role} response had no output text")
    return "".join(pieces)


def _target_config() -> dict[str, str] | None:
    enabled_value = os.environ.get("AUTODATA_TARGET_ENABLED", "1").strip().lower()
    if enabled_value in {"1", "true", "yes"}:
        enabled = True
    elif enabled_value in {"0", "false", "no"}:
        enabled = False
    else:
        raise RuntimeError(
            "AUTODATA_TARGET_ENABLED must be one of 1, 0, true, false, yes, or no"
        )
    values = {name: os.environ.get(name, "").strip() for name in _TARGET_ENV}
    configured = {name for name, value in values.items() if value}
    if not enabled:
        if configured:
            raise RuntimeError(
                "target settings must be absent when AUTODATA_TARGET_ENABLED=0"
            )
        return None
    missing = sorted(set(_TARGET_ENV) - configured)
    if missing:
        raise RuntimeError(
            "target inference requires all target settings; missing "
            + ", ".join(missing)
        )
    checkpoint_hash = values["AUTODATA_TARGET_CHECKPOINT_HASH"].lower()
    digest = checkpoint_hash.removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RuntimeError("AUTODATA_TARGET_CHECKPOINT_HASH must be a SHA-256 digest")
    values["AUTODATA_TARGET_CHECKPOINT_HASH"] = "sha256:" + digest
    values["AUTODATA_TARGET_URL"] = values["AUTODATA_TARGET_URL"].rstrip("/")
    return values
