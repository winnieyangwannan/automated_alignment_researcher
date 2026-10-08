"""Kimi Code CLI adapter for the autonomous research loop."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class KimiTextBlock:
    text: str


@dataclass
class KimiToolUseBlock:
    name: str
    input: dict[str, Any]


@dataclass
class KimiAssistantMessage:
    content: list[KimiTextBlock | KimiToolUseBlock]


@dataclass
class KimiAgentResult:
    success: bool
    output: dict[str, Any]
    duration: float
    iteration_count: int
    error: Optional[str] = None


class KimiAgent:
    """Run one AAR session through Kimi Code's structured prompt mode."""

    def __init__(
        self,
        name: str,
        workspace: Path,
        *,
        model: Optional[str] = None,
        cli_path: Optional[str] = None,
        message_callback: Optional[Callable[[KimiAssistantMessage], None]] = None,
        system_prompt: Optional[str] = None,
        include_prior_work: bool = True,
    ) -> None:
        self.name = name
        self.workspace = Path(workspace)
        self.model = model
        self.cli_path = cli_path
        self.message_callback = message_callback
        self.system_prompt = system_prompt
        self.include_prior_work = include_prior_work

    async def execute(self, task: str) -> KimiAgentResult:
        start_time = time.time()
        try:
            return await self._execute_once(task, start_time)
        except Exception as error:
            return KimiAgentResult(
                success=False,
                output={},
                duration=time.time() - start_time,
                iteration_count=0,
                error=str(error),
            )

    async def _execute_once(self, task: str, start_time: float) -> KimiAgentResult:
        executable = self.cli_path or shutil.which("kimi")
        if not executable:
            raise RuntimeError(
                "Kimi backend requires an executable KIMI_CLI_PATH or `kimi` on PATH"
            )

        command = [executable]
        if self.model:
            command.extend(["--model", self.model])
        prompt = f"{self.system_prompt}\n\n{task}" if self.system_prompt else task
        command.extend(["--prompt", prompt, "--output-format", "stream-json"])

        output: dict[str, Any] = {
            "text_outputs": [],
            "tool_uses": [],
            "raw_messages": [],
        }
        iteration_count = 0

        with tempfile.TemporaryDirectory(prefix="aar-kimi-") as temp_dir:
            env = self._build_environment(Path(temp_dir))
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.workspace,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=10 * 1024 * 1024,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            stderr_task = asyncio.create_task(process.stderr.read())

            try:
                async for raw_line in process.stdout:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise RuntimeError(
                            f"Kimi emitted invalid stream-json output: {line[:200]}"
                        ) from error
                    output["raw_messages"].append(event)
                    message = self._assistant_message(event)
                    if message is None:
                        continue
                    for block in message.content:
                        if isinstance(block, KimiTextBlock):
                            output["text_outputs"].append(block.text)
                        else:
                            iteration_count += 1
                            output["tool_uses"].append(
                                {"tool": block.name, "input": block.input}
                            )
                    log_message = self._format_message(message)
                    if log_message:
                        print(log_message)
                    if self.message_callback:
                        self.message_callback(message)

                return_code = await process.wait()
                stderr = (await stderr_task).decode("utf-8", errors="replace").strip()
            except BaseException:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                if not stderr_task.done():
                    stderr_task.cancel()
                raise

        if return_code != 0:
            detail = stderr or self._event_error(output["raw_messages"])
            raise RuntimeError(
                f"Kimi Code exited with status {return_code}: "
                f"{detail or 'no error detail'}"
            )
        if not output["text_outputs"] and not output["tool_uses"]:
            raise RuntimeError("Kimi Code ended without an assistant response")

        output["result_message"] = (
            output["text_outputs"][-1] if output["text_outputs"] else ""
        )
        return KimiAgentResult(
            success=True,
            output=output,
            duration=time.time() - start_time,
            iteration_count=iteration_count,
        )

    def _build_environment(self, overlay_home: Path) -> dict[str, str]:
        """Create an isolated Kimi home with AAR's MCP servers overlaid."""
        env = os.environ.copy()
        source_home = Path(
            env.get("KIMI_CODE_HOME") or Path.home() / ".kimi-code"
        ).expanduser()
        if source_home.exists():
            for child in source_home.iterdir():
                if child.name == "mcp.json":
                    continue
                (overlay_home / child.name).symlink_to(
                    child, target_is_directory=child.is_dir()
                )

        mcp_config: dict[str, Any] = {"mcpServers": {}}
        source_mcp = source_home / "mcp.json"
        if source_mcp.exists():
            try:
                loaded = json.loads(source_mcp.read_text())
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError(f"Invalid Kimi MCP config at {source_mcp}: {error}")
            if not isinstance(loaded, dict) or not isinstance(
                loaded.get("mcpServers", {}), dict
            ):
                raise RuntimeError(
                    f"Invalid Kimi MCP config at {source_mcp}: "
                    "mcpServers must be an object"
                )
            mcp_config = loaded
            mcp_config.setdefault("mcpServers", {})

        server_args = ["-m", "aar.research_loop.tools.kimi_mcp_server"]
        mcp_config["mcpServers"]["server-api-tools"] = {
            "command": sys.executable,
            "args": [*server_args, "--server", "server-api-tools"],
            "cwd": str(self.workspace),
        }
        if self.include_prior_work:
            mcp_config["mcpServers"]["prior-work-tools"] = {
                "command": sys.executable,
                "args": [*server_args, "--server", "prior-work-tools"],
                "cwd": str(self.workspace),
            }
        (overlay_home / "mcp.json").write_text(
            json.dumps(mcp_config, indent=2) + "\n"
        )

        python_path = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{self.workspace}{os.pathsep}{python_path}"
            if python_path
            else str(self.workspace)
        )
        env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
        env["KIMI_CODE_HOME"] = str(overlay_home)
        return env

    @staticmethod
    def _assistant_message(event: Any) -> Optional[KimiAssistantMessage]:
        if not isinstance(event, dict) or event.get("role") != "assistant":
            return None
        blocks: list[KimiTextBlock | KimiToolUseBlock] = []
        content = event.get("content")
        if isinstance(content, str) and content:
            blocks.append(KimiTextBlock(content))
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        blocks.append(KimiTextBlock(text))

        for tool_call in event.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") or {}
            name = function.get("name")
            if not isinstance(name, str) or not name:
                continue
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": arguments}
            if not isinstance(arguments, dict):
                arguments = {"value": arguments}
            blocks.append(KimiToolUseBlock(name=name, input=arguments))
        return KimiAssistantMessage(blocks) if blocks else None

    @staticmethod
    def _event_error(events: list[Any]) -> str:
        for event in reversed(events):
            if not isinstance(event, dict):
                continue
            for key in ("error", "error_message"):
                value = event.get(key)
                if value:
                    return value if isinstance(value, str) else json.dumps(value)
        return ""

    def _format_message(self, message: KimiAssistantMessage) -> Optional[str]:
        timestamp = datetime.now().strftime("%H:%M:%S")
        parts = []
        for content in message.content:
            if isinstance(content, KimiTextBlock):
                parts.append(f"[{timestamp}] [{self.name}] {content.text[:200]}")
            else:
                parts.append(f"[{timestamp}] [{self.name}] -> {content.name}")
        return "\n".join(parts) if parts else None
