"""Tool-free Claude semantic worker for a host-owned AutoData action."""

from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .semantic_worker import (
    ActionContext,
    MalformedSemanticOutcome,
    SemanticOutcome,
)


@contextmanager
def _without_autodata_capability() -> Iterator[None]:
    """Keep the broker capability out of the model subprocess environment."""

    value = os.environ.pop("AAR_AUTODATA_CAPABILITY", None)
    try:
        yield
    finally:
        if value is not None:
            os.environ["AAR_AUTODATA_CAPABILITY"] = value


class ClaudeWorker:
    """Ask Claude for one typed proposal without granting filesystem tools."""

    backend_name = "claude"

    def __init__(self, agent_factory: Callable[[ActionContext], Any] | None = None):
        self._agent_factory = agent_factory

    @staticmethod
    def _task(context: ActionContext) -> str:
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
            "update, it must be the complete replacement workspace object.\n\nACTION:\n"
            + json.dumps(payload, sort_keys=True, indent=2)
        )

    def _agent(self, context: ActionContext) -> Any:
        if self._agent_factory is not None:
            return self._agent_factory(context)
        from aar.research_loop.agent import BaseAgent

        return BaseAgent(
            name=f"autodata-clarify-{context.action_id}",
            allowed_tools=[],
            workspace=Path.cwd(),
            mcp_servers={},
            model=os.getenv("AAR_AGENT_MODEL", "claude-opus-4-8"),
            cli_path=os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude"),
            permission_mode="bypassPermissions",
            system_prompt=(
                "You are a tool-free semantic worker. Native AutoData and trusted host "
                "code own state, files, leases, transitions, budgets, and receipts."
            ),
            tools=[],
            setting_sources=[],
            strict_mcp_config=True,
            progress_timeout_seconds=float(
                os.getenv("AAR_AUTODATA_CLARIFY_PROGRESS_SECONDS", "600")
            ),
        )

    @staticmethod
    def _parse(output: object) -> SemanticOutcome:
        candidates: list[str] = []
        if isinstance(output, dict):
            candidates.extend(
                value
                for value in output.get("text_outputs", [])
                if isinstance(value, str)
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
            raise MalformedSemanticOutcome("Claude returned no unique JSON outcome")
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
            raise MalformedSemanticOutcome("Claude outcome is missing a field") from error
        if (
            not isinstance(action_id, str)
            or not isinstance(input_revision, int)
            or not isinstance(input_digest, str)
            or decision not in {"confirm", "update"}
            or not isinstance(summary, str)
            or not isinstance(decisions, list)
            or (updated_workspace is not None and not isinstance(updated_workspace, dict))
        ):
            raise MalformedSemanticOutcome("Claude outcome has invalid field types")
        return SemanticOutcome(
            action_id=action_id,
            input_revision=input_revision,
            input_digest=input_digest,
            decision=decision,
            summary=summary,
            decisions=tuple(decisions),
            updated_workspace=updated_workspace,
        )

    async def perform(self, context: ActionContext) -> SemanticOutcome:
        with _without_autodata_capability():
            response = await self._agent(context).execute(task=self._task(context))
        if not getattr(response, "success", False):
            raise RuntimeError("Claude semantic worker failed")
        return self._parse(getattr(response, "output", None))
