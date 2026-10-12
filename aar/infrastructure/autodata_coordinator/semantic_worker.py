"""Typed, backend-neutral semantic boundary for one native AutoData action."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, TypeAlias


@dataclass(frozen=True, slots=True)
class ActionContext:
    """Sanitized immutable inputs; no lease, native control, or writable path."""

    action_id: str
    workspace_id: str
    input_revision: int
    input_digest: str
    instructions: str
    allowed_paths: tuple[str, ...]
    required_outputs: tuple[str, ...]
    workspace: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SemanticOutcome:
    """A worker proposal bound to the exact native action input."""

    action_id: str
    input_revision: int
    input_digest: str
    decision: Literal["confirm", "update"]
    summary: str
    decisions: tuple[Any, ...]
    updated_workspace: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Immutable execution evidence for one native ``analyze_results`` action."""

    action_id: str
    execution_id: str
    input_revision: int
    input_digest: str
    instructions: str
    required_outputs: tuple[str, ...]
    evidence: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    """A scoped analysis proposal bound to one execution revision."""

    action_id: str
    input_revision: int
    input_digest: str
    proposal: str
    dashboard_summary: Mapping[str, str]


WorkerContext: TypeAlias = ActionContext | AnalysisContext
WorkerOutcome: TypeAlias = SemanticOutcome | AnalysisOutcome


class MalformedSemanticOutcome(RuntimeError):
    """A retryable model-output shape failure."""


class SemanticWorker(Protocol):
    @property
    def backend_name(self) -> str: ...

    async def perform(self, context: WorkerContext) -> WorkerOutcome: ...


def semantic_task(context: WorkerContext) -> str:
    """Build one backend-neutral request for an allowlisted native action."""

    if isinstance(context, AnalysisContext):
        payload = {
            "action_id": context.action_id,
            "execution_id": context.execution_id,
            "input_revision": context.input_revision,
            "input_digest": context.input_digest,
            "instructions": context.instructions,
            "required_outputs": list(context.required_outputs),
            "evidence": list(context.evidence),
        }
        return (
            "Analyze exactly this native AutoData analyze_results input. You have no "
            "tools and must not perform lifecycle control or filesystem work. Use only "
            "the attached visible evidence; hidden selection inputs are unavailable. "
            "Return one JSON object with the unchanged action_id, input_revision, and "
            "input_digest; proposal as one non-empty string describing one scoped "
            "change; and dashboard_summary as an object containing non-empty headline, "
            "summary, and next_step strings. Return only the JSON object, with no "
            "Markdown fence or surrounding prose.\n\nACTION:\n"
            + json.dumps(payload, sort_keys=True, indent=2)
        )

    payload = {
        "action_id": context.action_id,
        "workspace_id": context.workspace_id,
        "input_revision": context.input_revision,
        "input_digest": context.input_digest,
        "instructions": context.instructions,
        "allowed_paths": list(context.allowed_paths),
        "required_outputs": list(context.required_outputs),
        "workspace": context.workspace,
    }
    return (
        "Review exactly this AutoData clarify_design input. You have no tools and "
        "must not perform lifecycle control or filesystem work. Return one JSON "
        "object with the unchanged action_id, input_revision, and input_digest; "
        "decision ('confirm' or 'update'); non-empty summary; decisions (array); "
        "and updated_workspace. For confirm, updated_workspace must be null. For "
        "update, it must be the complete replacement workspace object. Return only "
        "the JSON object, with no Markdown fence or surrounding prose.\n\nACTION:\n"
        + json.dumps(payload, sort_keys=True, indent=2)
    )


def parse_semantic_outcome(output: object, *, backend: str) -> SemanticOutcome:
    """Parse the one shared semantic-outcome contract from a model response."""

    candidates: list[str] = []
    if isinstance(output, dict):
        candidates.extend(
            value for value in output.get("text_outputs", []) if isinstance(value, str)
        )
        result_message = output.get("result_message")
        if isinstance(result_message, str):
            candidates.append(result_message)
    parsed: list[dict[str, Any]] = []
    for candidate in candidates:
        stripped = candidate.strip()
        fenced = re.findall(
            r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL
        )
        for raw in [stripped, *fenced]:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value not in parsed:
                parsed.append(value)
    if len(parsed) != 1:
        raise MalformedSemanticOutcome(f"{backend} returned no unique JSON outcome")
    value = parsed[0]
    try:
        action_id = value["action_id"]
        input_revision = value["input_revision"]
        input_digest = value["input_digest"]
        decision = value["decision"]
        summary = value["summary"]
        decisions = value["decisions"]
        updated_workspace = value["updated_workspace"]
    except KeyError as error:
        raise MalformedSemanticOutcome(
            f"{backend} outcome is missing a field"
        ) from error
    if (
        not isinstance(action_id, str)
        or not isinstance(input_revision, int)
        or not isinstance(input_digest, str)
        or decision not in {"confirm", "update"}
        or not isinstance(summary, str)
        or not isinstance(decisions, list)
        or (updated_workspace is not None and not isinstance(updated_workspace, dict))
    ):
        raise MalformedSemanticOutcome(f"{backend} outcome has invalid field types")
    return SemanticOutcome(
        action_id=action_id,
        input_revision=input_revision,
        input_digest=input_digest,
        decision=decision,
        summary=summary,
        decisions=tuple(decisions),
        updated_workspace=updated_workspace,
    )


def parse_analysis_outcome(output: object, *, backend: str) -> AnalysisOutcome:
    """Parse one typed ``analyze_results`` response."""

    candidates: list[str] = []
    if isinstance(output, dict):
        candidates.extend(
            value for value in output.get("text_outputs", []) if isinstance(value, str)
        )
        result_message = output.get("result_message")
        if isinstance(result_message, str):
            candidates.append(result_message)
    parsed: list[dict[str, Any]] = []
    for candidate in candidates:
        stripped = candidate.strip()
        fenced = re.findall(
            r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL
        )
        for raw in [stripped, *fenced]:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value not in parsed:
                parsed.append(value)
    if len(parsed) != 1:
        raise MalformedSemanticOutcome(
            f"{backend} returned no unique JSON analysis outcome"
        )
    value = parsed[0]
    try:
        action_id = value["action_id"]
        input_revision = value["input_revision"]
        input_digest = value["input_digest"]
        proposal = value["proposal"]
        dashboard = value["dashboard_summary"]
    except KeyError as error:
        raise MalformedSemanticOutcome(
            f"{backend} analysis outcome is missing a field"
        ) from error
    if (
        not isinstance(action_id, str)
        or not isinstance(input_revision, int)
        or not isinstance(input_digest, str)
        or not isinstance(proposal, str)
        or not proposal.strip()
        or not isinstance(dashboard, dict)
        or set(dashboard) != {"headline", "summary", "next_step"}
        or any(
            not isinstance(item, str) or not item.strip() for item in dashboard.values()
        )
    ):
        raise MalformedSemanticOutcome(
            f"{backend} analysis outcome has invalid field types"
        )
    return AnalysisOutcome(
        action_id=action_id,
        input_revision=input_revision,
        input_digest=input_digest,
        proposal=proposal,
        dashboard_summary=dict(dashboard),
    )
