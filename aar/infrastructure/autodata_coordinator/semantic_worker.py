"""Typed, backend-neutral semantic boundary for one native AutoData action."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol


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


class MalformedSemanticOutcome(RuntimeError):
    """A retryable model-output shape failure."""


class SemanticWorker(Protocol):
    @property
    def backend_name(self) -> str: ...

    async def perform(self, context: ActionContext) -> SemanticOutcome: ...
