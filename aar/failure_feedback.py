"""Bounded, secret-safe failure feedback with digest-bound evidence pointers."""

from __future__ import annotations

import re
from typing import Any, Literal

SCHEMA = "aar.failure-feedback/v1"
FailureDisposition = Literal["retry_operation", "advance_session", "halt"]
_DISPOSITIONS: set[str] = {"retry_operation", "advance_session", "halt"}

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


_ERROR_GUIDANCE = {
    "required_completion_missing": (
        "Start a fresh research session from the durable lifecycle state; resume an "
        "approved run instead of creating or submitting a duplicate."
    ),
    "required_checkpoint_missing": (
        "Start a fresh research session and execute the next required checkpoint "
        "tool with its host-provided arguments."
    ),
    "research_session_stalled": (
        "Start a fresh research session from the last durable milestone and avoid "
        "repeating the unchanged contract, proposal, or run state."
    ),
    "training_dataset_empty": (
        "Validate the final post-filter dataset count and one concrete sample before "
        "constructing the trainer. Preference trainers require nonempty string "
        "chosen and rejected fields."
    ),
    "training_preference_schema_invalid": (
        "Normalize every preference example to nonempty string prompt, chosen, and "
        "rejected fields before constructing the trainer."
    ),
    "training_loss_missing": (
        "Make the model return a finite scalar loss whenever labels are supplied, "
        "and verify this with the one-step training contract before resubmission."
    ),
    "training_api_mismatch": (
        "Reconcile the candidate with the locked Transformers, TRL, PEFT, and Trainer "
        "signatures, then rerun the method contract and one-step smoke test."
    ),
    "training_dataset_interface_invalid": (
        "Convert Python list or dictionary rows to a datasets.Dataset before passing "
        "train_dataset to Trainer or SFTTrainer, then validate one batch in the "
        "one-step smoke test."
    ),
    "training_method_config_invalid": (
        "Declare and initialize every required MethodConfig field, including output_dir, "
        "dry_run, and smoke_run, then rerun the dry-run and one-step smoke contracts."
    ),
    "training_optional_integer_invalid": (
        "Replace unset optional values used by arithmetic or comparisons with explicit "
        "validated integers, then exercise the full-data branch in the one-step smoke "
        "test before resubmission."
    ),
    "training_peft_target_mismatch": (
        "Use the validated Gemma-4 PEFT target_modules regex as one string, assert that "
        "it matches trainable modules, and rerun the one-step training contract."
    ),
    "training_tensor_shape_mismatch": (
        "Inspect one tokenized batch and the model/collator input contract, correct the "
        "rank or shape mismatch, and rerun one forward-and-loss step."
    ),
    "training_cuda_out_of_memory": (
        "Reduce peak training memory with a smaller microbatch or sequence length and "
        "gradient accumulation/checkpointing, then rerun the one-step GPU smoke test."
    ),
    "training_tokenizer_configuration_invalid": (
        "Set and validate the tokenizer padding token, padding side, and matching model "
        "configuration before constructing the trainer."
    ),
    "training_python_exception": (
        "Inspect the candidate's public method contract and training code, correct "
        "the Python failure, and do not resubmit the unchanged method."
    ),
    "training_process_failed": (
        "Use the typed training failure and retained operator evidence to classify "
        "the cause before revising or retrying the candidate."
    ),
}

_STAGE_GUIDANCE = {
    "research_session": "Repair or restart the research session from durable state.",
    "research_tool": "Correct the tool request or use the documented alternative.",
    "proposal_review": "Revise the same method from the proposal-review verdict.",
    "proposal_submission": "Correct the proposal payload and resubmit the same method.",
    "training_submission": (
        "Reconcile the approved run and its submission receipt before retrying."
    ),
    "training": "Diagnose the candidate or infrastructure failure before the next method session.",
    "evaluation_submission": (
        "Repair the evaluator handoff without changing the approved run identity."
    ),
    "evaluation": "Use the typed evaluator failure without exposing private examples or scores.",
    "evaluation_scoring": (
        "Inspect evaluator-private diagnostics and keep private content isolated."
    ),
    "result_publication": (
        "Retry publication against the same scored run without duplicating training."
    ),
    "autodata_bootstrap": "Repair the trusted AutoData workspace bootstrap before continuing.",
    "autodata_approval": "Resolve the delegated approval failure before continuing the lifecycle.",
    "autodata_action": "Repair the scoped AutoData action or its trusted result record.",
    "autodata_grounding": "Repair and revalidate the grounding artifact before production.",
    "autodata_lifecycle": "Reconcile the trusted AutoData lifecycle state before continuing.",
    "autodata_production": "Repair the production execution while preserving its lineage.",
    "autodata_handoff": "Repair the verified training handoff before submission.",
}


def _failure_family_guidance(error_code: str) -> str | None:
    """Return actionable guidance for a named production failure family.

    Exact codes above describe failures that need a particular repair contract.
    Families keep newly added codes useful while the repository-wide coverage
    test makes completely unclassified names visible during review.
    """

    if error_code.startswith("training_"):
        return (
            "Preserve the approved run identity, inspect the retained training "
            "evidence, and distinguish a candidate-code defect from an infrastructure "
            "failure. Revise the method for a candidate defect; retry only the same "
            "host-owned operation for an infrastructure failure."
        )
    if error_code.startswith(
        ("evaluation_", "model_evaluation_", "prediction_evaluation_")
    ):
        return (
            "Use evaluator-private diagnostics to classify the failure, preserve the "
            "adapter and run identity, and retry only infrastructure work. Do not "
            "expose private evaluation examples, partial scores, or judge output to "
            "research."
        )
    if error_code.startswith("proposal_"):
        return (
            "Apply the proposal verdict to the same candidate, correct every named "
            "code or paper defect, rerun its contract, and resubmit without inventing "
            "a run ID."
        )
    if error_code.startswith(
        (
            "autodata_",
            "workspace_",
            "grounding_",
            "production_",
            "meta_to_",
        )
    ):
        return (
            "Reconcile the trusted AutoData record with its durable state and schema, "
            "repair the named artifact or transition, validate it, and then resume "
            "without duplicating completed lifecycle work."
        )
    if error_code.startswith(
        ("protected_file_", "orchestration_", "integrity_", "self_containment_")
    ):
        return (
            "Treat this as a host-owned integrity failure: stop model-controlled "
            "progress, restore the expected trusted source or invariant, and rerun "
            "verification before resuming."
        )
    if error_code.startswith(("kimi_", "research_", "agent_", "required_")):
        return (
            "Preserve durable artifacts, correct the named research-session failure, "
            "and continue from the next unmet lifecycle milestone rather than "
            "replaying completed work."
        )
    if error_code.startswith(
        (
            "finding_",
            "literature_",
            "leaderboard_",
            "result_",
            "run_id_",
            "snapshot_",
            "authoritative_score_",
            "local_finding_",
        )
    ):
        return (
            "Retry the named read or publication operation against the same durable "
            "identity, first checking whether it already completed to avoid duplicate "
            "records."
        )
    if error_code.startswith(("invalid_failure_", "mcp_tool_", "lifecycle_")):
        return (
            "Repair the named host/tool contract, validate the structured result, and "
            "retry from the last durable lifecycle milestone."
        )
    if error_code.endswith("_invalid_json"):
        return (
            "Regenerate the named artifact as valid JSON matching its required schema, "
            "then validate it before retrying."
        )
    if error_code.endswith(("_invalid", "_mismatch")):
        return (
            "Compare the observed artifact or identity with the documented contract, "
            "repair the mismatch, and rerun validation before continuing."
        )
    if error_code.endswith(("_missing", "_incomplete")):
        return (
            "Restore or complete the named required artifact from durable state; do "
            "not fabricate identifiers or repeat already completed operations."
        )
    if error_code.endswith(("_timeout", "_stalled", "_unavailable", "_overloaded")):
        return (
            "Check durable receipts and live process state, then retry or resume the "
            "same operation after capacity recovers without duplicating completed work."
        )
    if error_code.endswith(("_failed", "_failure", "_rejected", "_incident")):
        return (
            "Use the retained operator evidence to classify the named failure, repair "
            "its concrete cause, and choose retry, session advance, or halt before "
            "continuing."
        )
    return None


def has_actionable_failure_guidance(error_code: str) -> bool:
    """Return whether an error code has exact or family-level recovery guidance."""

    return (
        error_code in _ERROR_GUIDANCE
        or _failure_family_guidance(error_code) is not None
    )


def failure_guidance(stage: str, error_code: str) -> str:
    """Return static, held-out-safe recovery guidance for every typed failure."""

    return (
        _ERROR_GUIDANCE.get(error_code)
        or _failure_family_guidance(error_code)
        or _STAGE_GUIDANCE.get(stage)
        or "Use the typed stage and error code to repair the failed operation."
    )


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
    disposition: FailureDisposition | None = None,
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
    if disposition is None:
        disposition = "retry_operation" if retryable else "halt"
    if disposition not in _DISPOSITIONS:
        raise ValueError("disposition must be retry_operation, advance_session, or halt")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "failed",
        "stage": stage,
        "error_code": error_code,
        "retryable": bool(retryable),
        "disposition": disposition,
        "exception_type": type(error).__name__,
        "summary": sanitize_failure_summary(
            error if public_summary is None else public_summary,
            limit=limit,
        ),
        "guidance": failure_guidance(stage, error_code),
    }
    return result


def feedback_from_exception(
    error: BaseException,
    *,
    error_code: str,
    stage: str,
    retryable: bool = False,
    disposition: FailureDisposition | None = None,
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
        disposition=disposition,
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
    disposition = value.get("disposition")
    if (
        value.get("schema") != SCHEMA
        or value.get("status") != "failed"
        or not isinstance(stage, str)
        or _STAGE.fullmatch(stage) is None
        or not isinstance(error_code, str)
        or _ERROR_CODE.fullmatch(error_code) is None
        or not isinstance(retryable, bool)
        or (disposition is not None and disposition not in _DISPOSITIONS)
    ):
        return None
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "failed",
        "stage": stage,
        "error_code": error_code,
        "retryable": retryable,
        "disposition": disposition or (
            "retry_operation" if retryable else "halt"
        ),
        "summary": sanitize_failure_summary(
            public_summary or f"{stage} failed ({error_code})"
        ),
        "guidance": failure_guidance(stage, error_code),
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
