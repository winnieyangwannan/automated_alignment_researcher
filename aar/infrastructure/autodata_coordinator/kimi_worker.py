"""One-turn, tool-free Kimi worker for a host-owned AutoData action."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Any

from aar.research_loop.kimi_agent import KimiAgent

from .semantic_worker import (
    AnalysisContext,
    MalformedSemanticOutcome,
    MutationContext,
    WorkerContext,
    WorkerOutcome,
    parse_analysis_outcome,
    parse_mutation_outcome,
    parse_semantic_outcome,
    semantic_task,
)

_DISALLOWED_TOOLS = (
    "Agent",
    "AgentSwarm",
    "Bash",
    "CreateGoal",
    "Edit",
    "Glob",
    "Grep",
    "Read",
    "SetGoalBudget",
    "Shell",
    "Skill",
    "Task",
    "TodoList",
    "UpdateGoal",
    "WaitFor",
    "WebFetch",
    "WebSearch",
    "Write",
)

_ENVIRONMENT_ALLOWLIST = (
    "AAR_KIMI_DISABLE_THINKING",
    "AAR_KIMI_EXPECTED_MODEL",
    "AAR_KIMI_PROVIDER_TYPE",
    "AAR_KIMI_SERVE_DEPLOYMENT",
    "AAR_SERVE_API_V2_ROOT",
    "HOME",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "KIMI_MODEL_CAPABILITIES",
    "KIMI_MODEL_MAX_COMPLETION_TOKENS",
    "KIMI_MODEL_MAX_CONTEXT_SIZE",
    "KIMI_MODEL_MAX_OUTPUT_SIZE",
    "KIMI_MODEL_REASONING_KEY",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "NO_PROXY",
    "PATH",
    "RAM_COMMON_ROOT",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
    "TERM",
    "TMPDIR",
    "USER",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


class KimiWorker:
    """Ask Kimi for one typed proposal without a lifecycle or tool loop."""

    backend_name = "kimi"

    def __init__(
        self,
        *,
        cli_path: str | None = None,
        model: str | None = None,
    ) -> None:
        self.cli_path = cli_path
        self.model = model

    @staticmethod
    def _profile() -> str:
        return "\n".join(
            [
                "---",
                "name: autodata-semantic-worker",
                "description: Tool-free typed AutoData semantic worker",
                f"disallowedTools: {json.dumps(_DISALLOWED_TOOLS)}",
                "---",
                "",
                "You are a tool-free semantic worker. Native AutoData and trusted ",
                "host code own state, files, leases, transitions, budgets, and receipts.",
                "Return only the requested JSON object and do not call any tool.",
                "",
            ]
        )

    @staticmethod
    def _environment(home: Path) -> dict[str, str]:
        env = {
            key: value
            for key in _ENVIRONMENT_ALLOWLIST
            if (value := os.environ.get(key)) is not None
        }
        KimiAgent.configure_serve_api_provider(env)
        env["KIMI_CODE_HOME"] = str(home)
        return env

    @staticmethod
    def _output(stdout: bytes) -> dict[str, Any]:
        output: dict[str, Any] = {
            "text_outputs": [],
            "tool_uses": [],
            "raw_messages": [],
            "raw_stdout": [],
        }
        for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                output["raw_stdout"].append(line)
                continue
            output["raw_messages"].append(event)
            if not isinstance(event, dict) or event.get("role") != "assistant":
                continue
            tool_calls = event.get("tool_calls") or []
            if tool_calls:
                output["tool_uses"].extend(tool_calls)
            content = event.get("content")
            if isinstance(content, str) and content:
                output["text_outputs"].append(content)
            elif isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict) or item.get("type") != "text":
                        continue
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        output["text_outputs"].append(text)
        if output["text_outputs"]:
            output["result_message"] = output["text_outputs"][-1]
        return output

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except TimeoutError:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()

    async def _execute(self, task: str) -> dict[str, Any]:
        executable = self.cli_path or os.getenv("KIMI_CLI_PATH") or shutil.which("kimi")
        if not executable:
            raise RuntimeError(
                "Kimi semantic worker requires KIMI_CLI_PATH or `kimi` on PATH"
            )
        with tempfile.TemporaryDirectory(prefix="aar-kimi-semantic-") as raw_home:
            home = Path(raw_home)
            (home / "config.toml").write_text("", encoding="utf-8")
            (home / "mcp.json").write_text(
                json.dumps({"mcpServers": {}}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            profile = home / "semantic-worker.md"
            profile.write_text(self._profile(), encoding="utf-8")
            command = [str(executable)]
            if self.model:
                command.extend(["--model", self.model])
            command.extend(
                [
                    "--agent-file",
                    str(profile),
                    "--prompt",
                    task,
                    "--output-format",
                    "stream-json",
                ]
            )
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=home,
                env=self._environment(home),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, _stderr = await process.communicate()
            except BaseException:
                await self._terminate(process)
                raise
            if process.returncode != 0:
                raise RuntimeError(
                    f"Kimi semantic worker exited with status {process.returncode}"
                )
            return self._output(stdout)

    async def perform(self, context: WorkerContext) -> WorkerOutcome:
        output = await self._execute(semantic_task(context))
        if output["tool_uses"]:
            raise MalformedSemanticOutcome(
                "Kimi semantic worker attempted a forbidden tool call"
            )
        if isinstance(context, AnalysisContext):
            return parse_analysis_outcome(output, backend="Kimi")
        if isinstance(context, MutationContext):
            return parse_mutation_outcome(output, backend="Kimi")
        return parse_semantic_outcome(output, backend="Kimi")
