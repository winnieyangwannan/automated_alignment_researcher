"""Tool-free Claude semantic worker for a host-owned AutoData action."""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .semantic_worker import (
    AnalysisContext,
    WorkerContext,
    WorkerOutcome,
    parse_analysis_outcome,
    parse_semantic_outcome,
    semantic_task,
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

    def __init__(self, agent_factory: Callable[[WorkerContext], Any] | None = None):
        self._agent_factory = agent_factory

    @staticmethod
    def _task(context: WorkerContext) -> str:
        return semantic_task(context)

    def _agent(self, context: WorkerContext) -> Any:
        if self._agent_factory is not None:
            return self._agent_factory(context)
        from aar.research_loop.agent import BaseAgent

        return BaseAgent(
            name=f"autodata-semantic-{context.action_id}",
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
                os.getenv(
                    "AAR_AUTODATA_SEMANTIC_PROGRESS_SECONDS",
                    os.getenv("AAR_AUTODATA_CLARIFY_PROGRESS_SECONDS", "600"),
                )
            ),
        )

    @staticmethod
    def _parse(output: object, context: WorkerContext) -> WorkerOutcome:
        if isinstance(context, AnalysisContext):
            return parse_analysis_outcome(output, backend="Claude")
        return parse_semantic_outcome(output, backend="Claude")

    async def perform(self, context: WorkerContext) -> WorkerOutcome:
        with _without_autodata_capability():
            response = await self._agent(context).execute(task=self._task(context))
        if not getattr(response, "success", False):
            raise RuntimeError("Claude semantic worker failed")
        return self._parse(getattr(response, "output", None), context)
