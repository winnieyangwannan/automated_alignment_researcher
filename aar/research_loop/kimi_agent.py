"""Kimi Code CLI adapter for the autonomous research loop."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
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
            "raw_stdout": [],
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
                    except json.JSONDecodeError:
                        # Kimi Code 2.1.1 can mirror terminal-tool output to
                        # stdout before emitting the corresponding JSON tool
                        # event. Preserve it without corrupting the JSONL
                        # session parser.
                        output["raw_stdout"].append(line)
                        continue
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
        self._apply_serve_api_provider(env)
        return env

    def _apply_serve_api_provider(self, env: dict[str, str]) -> None:
        """Resolve a live serve_api_v2 proxy without exposing its API key."""
        deployment = env.get("AAR_KIMI_SERVE_DEPLOYMENT", "").strip()
        if not deployment:
            return
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", deployment):
            raise RuntimeError("AAR_KIMI_SERVE_DEPLOYMENT is invalid")

        root = Path(
            env.get("AAR_SERVE_API_V2_ROOT")
            or Path(env.get("RAM_COMMON_ROOT", str(Path.home() / "ram_common")))
            / "vllm_tools"
            / "serve_api_v2"
        ).expanduser()
        serve = root / "serve.sh"
        if not serve.is_file():
            raise RuntimeError(f"serve_api_v2 launcher not found at {serve}")
        result = subprocess.run(
            [str(serve), "generate-opencode-config", deployment],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"serve_api_v2 could not resolve deployment {deployment}"
            )
        try:
            config = json.loads(result.stdout)
            providers = config["provider"]
            if not isinstance(providers, dict) or len(providers) != 1:
                raise ValueError("expected exactly one provider")
            provider = next(iter(providers.values()))
            options = provider["options"]
            models = provider["models"]
            if not isinstance(models, dict) or len(models) != 1:
                raise ValueError("expected exactly one served model")
            model = next(iter(models))
            base_url = options["baseURL"]
            api_key = options["apiKey"]
            if not isinstance(base_url, str) or not base_url.startswith(
                ("http://", "https://")
            ):
                raise ValueError("invalid proxy base URL")
            if not isinstance(api_key, str) or not api_key:
                raise ValueError("missing proxy API key")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"serve_api_v2 returned invalid config for {deployment}"
            ) from error

        expected_model = env.get("AAR_KIMI_EXPECTED_MODEL", "").strip()
        if expected_model and model != expected_model:
            raise RuntimeError(
                f"serve_api_v2 model mismatch: expected {expected_model}, got {model}"
            )
        env.update(
            {
                "KIMI_MODEL_NAME": model,
                "KIMI_MODEL_PROVIDER_TYPE": "openai",
                "KIMI_MODEL_BASE_URL": base_url,
                "KIMI_MODEL_API_KEY": api_key,
                "KIMI_MODEL_MAX_CONTEXT_SIZE": env.get(
                    "KIMI_MODEL_MAX_CONTEXT_SIZE", "262144"
                ),
                "KIMI_MODEL_MAX_OUTPUT_SIZE": env.get(
                    "KIMI_MODEL_MAX_OUTPUT_SIZE", "16384"
                ),
                "KIMI_MODEL_CAPABILITIES": env.get(
                    "KIMI_MODEL_CAPABILITIES", "thinking,tool_use"
                ),
                "KIMI_MODEL_REASONING_KEY": env.get(
                    "KIMI_MODEL_REASONING_KEY", "reasoning_content"
                ),
            }
        )

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
