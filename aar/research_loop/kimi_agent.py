"""Kimi Code CLI adapter for the autonomous research loop."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator, Optional
from urllib.parse import urlsplit

import requests


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


def _policy_proxy_handler(
    *, upstream_origin: str, upstream_api_key: str, allowed_prefix: str
) -> type[BaseHTTPRequestHandler]:
    """Build a loopback handler that adds the vLLM Kimi thinking control."""

    class RequestPolicyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._forward()

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._forward()

        def log_message(self, _format: str, *args: Any) -> None:
            return

        def _forward(self) -> None:
            request_path = urlsplit(self.path).path
            if allowed_prefix and not (
                request_path == allowed_prefix
                or request_path.startswith(f"{allowed_prefix}/")
            ):
                self.send_error(404)
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            if self.command == "POST" and request_path.endswith(
                "/chat/completions"
            ):
                try:
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError("request body must be an object")
                    template_options = payload.setdefault(
                        "chat_template_kwargs", {}
                    )
                    if not isinstance(template_options, dict):
                        raise ValueError("chat_template_kwargs must be an object")
                    template_options["enable_thinking"] = False
                    body = json.dumps(payload).encode()
                except (json.JSONDecodeError, ValueError) as error:
                    self.send_error(400, str(error))
                    return

            headers = {
                name: value
                for name, value in self.headers.items()
                if name.lower()
                not in {
                    "accept-encoding",
                    "authorization",
                    "connection",
                    "content-length",
                    "host",
                    "transfer-encoding",
                }
            }
            headers["Authorization"] = f"Bearer {upstream_api_key}"
            try:
                with requests.request(
                    self.command,
                    f"{upstream_origin}{self.path}",
                    headers=headers,
                    data=body or None,
                    stream=True,
                    timeout=(30, 3600),
                ) as response:
                    self.send_response(response.status_code)
                    for name, value in response.headers.items():
                        if name.lower() in {
                            "connection",
                            "content-encoding",
                            "content-length",
                            "transfer-encoding",
                        }:
                            continue
                        self.send_header(name, value)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            self.wfile.write(chunk)
                            self.wfile.flush()
            except requests.RequestException:
                self.send_error(502, "upstream model endpoint request failed")

    return RequestPolicyHandler


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
        completion_tool: Optional[str] = None,
        max_continuations: int = 24,
        disallowed_tools: Optional[list[str]] = None,
    ) -> None:
        self.name = name
        self.workspace = Path(workspace)
        self.model = model
        self.cli_path = cli_path
        self.message_callback = message_callback
        self.system_prompt = system_prompt
        self.include_prior_work = include_prior_work
        self.completion_tool = completion_tool
        self.max_continuations = max_continuations
        self.disallowed_tools = disallowed_tools or []

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

        prompt = task

        output: dict[str, Any] = {
            "text_outputs": [],
            "tool_uses": [],
            "raw_messages": [],
            "raw_stdout": [],
        }
        iteration_count = 0
        continuation_count = 0

        with tempfile.TemporaryDirectory(prefix="aar-kimi-") as temp_dir:
            overlay_home = Path(temp_dir)
            env = self._build_environment(overlay_home)
            agent_file = self._write_agent_profile(overlay_home)
            with self._request_policy_proxy(env):
                while True:
                    command = [executable]
                    if self.model:
                        command.extend(["--model", self.model])
                    if continuation_count:
                        command.append("--continue")
                        if self.completion_tool == "share_finding":
                            current_prompt = (
                                "Continue executing the requested research iteration now. "
                                "Do not merely announce, summarize, or promise a next action. "
                                "Use the available tools and do not stop until evaluate_model "
                                "has returned and share_finding has succeeded."
                            )
                        else:
                            current_prompt = (
                                "Continue executing the requested task now. Do not merely "
                                "announce, summarize, or promise a next action. Use the "
                                f"available tools and call {self.completion_tool}."
                            )
                    else:
                        if agent_file is not None:
                            command.extend(["--agent-file", str(agent_file)])
                        current_prompt = prompt
                    command.extend(
                        ["--prompt", current_prompt, "--output-format", "stream-json"]
                    )
                    return_code, stderr, new_tool_uses = await self._run_command(
                        command, env, output
                    )
                    iteration_count += new_tool_uses
                    if return_code != 0:
                        detail = stderr or self._event_error(output["raw_messages"])
                        raise RuntimeError(
                            f"Kimi Code exited with status {return_code}: "
                            f"{detail or 'no error detail'}"
                        )
                    if not self.completion_tool or self._completion_tool_used(output):
                        break
                    if continuation_count >= self.max_continuations:
                        raise RuntimeError(
                            "Kimi stopped before calling the required completion tool "
                            f"{self.completion_tool} after {self.max_continuations} "
                            "continuations"
                        )
                    continuation_count += 1
                    print(
                        f"[Kimi] resuming incomplete session "
                        f"({continuation_count}/{self.max_continuations})"
                    )

        if not output["text_outputs"] and not output["tool_uses"]:
            raise RuntimeError("Kimi Code ended without an assistant response")

        output["continuations"] = continuation_count
        output["result_message"] = (
            output["text_outputs"][-1] if output["text_outputs"] else ""
        )
        return KimiAgentResult(
            success=True,
            output=output,
            duration=time.time() - start_time,
            iteration_count=iteration_count,
        )

    async def _run_command(
        self,
        command: list[str],
        env: dict[str, str],
        output: dict[str, Any],
    ) -> tuple[int, str, int]:
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
        tool_uses = 0
        try:
            async for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Kimi Code 2.1.1 can mirror terminal-tool output to stdout
                    # before emitting the corresponding JSON tool event.
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
                        tool_uses += 1
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
            if stderr:
                prior = output.get("stderr")
                output["stderr"] = f"{prior}\n{stderr}".strip() if prior else stderr
            return return_code, stderr, tool_uses
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            if not stderr_task.done():
                stderr_task.cancel()
            raise

    def _completion_tool_used(self, output: dict[str, Any]) -> bool:
        expected = self.completion_tool
        return bool(
            expected
            and any(
                item.get("tool") == expected
                or str(item.get("tool", "")).endswith(f"__{expected}")
                for item in output["tool_uses"]
            )
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

    def _write_agent_profile(self, overlay_home: Path) -> Optional[Path]:
        """Materialize Kimi Code system instructions as a real agent profile."""
        if not self.system_prompt and not self.disallowed_tools:
            return None
        profile = overlay_home / "aar-agent.md"
        frontmatter = [
            "---",
            "name: aar-researcher",
            "description: Noninteractive automated alignment researcher",
        ]
        if self.disallowed_tools:
            frontmatter.append(
                f"disallowedTools: {json.dumps(self.disallowed_tools)}"
            )
        frontmatter.extend(
            [
                "---",
                "",
                self.system_prompt
                or "Complete the user's task noninteractively with the available tools.",
                "",
            ]
        )
        profile.write_text("\n".join(frontmatter))
        return profile

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
        provider_type = env.get("AAR_KIMI_PROVIDER_TYPE", "openai").strip()
        if provider_type not in {"openai", "kimi"}:
            raise RuntimeError(
                "AAR_KIMI_PROVIDER_TYPE must be either openai or kimi"
            )
        env.update(
            {
                "KIMI_MODEL_NAME": model,
                "KIMI_MODEL_PROVIDER_TYPE": provider_type,
                "KIMI_MODEL_BASE_URL": base_url,
                "KIMI_MODEL_API_KEY": api_key,
                "KIMI_MODEL_MAX_CONTEXT_SIZE": env.get(
                    "KIMI_MODEL_MAX_CONTEXT_SIZE", "262144"
                ),
                "KIMI_MODEL_MAX_OUTPUT_SIZE": env.get(
                    "KIMI_MODEL_MAX_OUTPUT_SIZE", "65536"
                ),
                "KIMI_MODEL_MAX_COMPLETION_TOKENS": env.get(
                    "KIMI_MODEL_MAX_COMPLETION_TOKENS", "65536"
                ),
                "KIMI_MODEL_CAPABILITIES": env.get(
                    "KIMI_MODEL_CAPABILITIES", "thinking,tool_use"
                ),
                "KIMI_MODEL_REASONING_KEY": env.get(
                    "KIMI_MODEL_REASONING_KEY", "reasoning_content"
                ),
            }
        )

    @contextlib.contextmanager
    def _request_policy_proxy(self, env: dict[str, str]) -> Iterator[None]:
        """Apply opt-in request fields unsupported by Kimi Code's provider config."""
        if env.get("AAR_KIMI_DISABLE_THINKING", "").lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            yield
            return

        upstream_base_url = env.get("KIMI_MODEL_BASE_URL", "")
        upstream_api_key = env.get("KIMI_MODEL_API_KEY", "")
        parsed = urlsplit(upstream_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(
                "AAR_KIMI_DISABLE_THINKING requires a valid KIMI_MODEL_BASE_URL"
            )
        if not upstream_api_key:
            raise RuntimeError(
                "AAR_KIMI_DISABLE_THINKING requires KIMI_MODEL_API_KEY"
            )
        if parsed.query or parsed.fragment:
            raise RuntimeError("KIMI_MODEL_BASE_URL cannot contain a query or fragment")

        upstream_origin = f"{parsed.scheme}://{parsed.netloc}"
        allowed_prefix = parsed.path.rstrip("/")
        handler = _policy_proxy_handler(
            upstream_origin=upstream_origin,
            upstream_api_key=upstream_api_key,
            allowed_prefix=allowed_prefix,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever,
            name="aar-kimi-request-policy",
            daemon=True,
        )
        thread.start()
        local_base_url = (
            f"http://127.0.0.1:{server.server_port}{allowed_prefix}"
        )
        env["KIMI_MODEL_BASE_URL"] = local_base_url
        env["KIMI_MODEL_API_KEY"] = "aar-local-request-policy"
        try:
            yield
        finally:
            env["KIMI_MODEL_BASE_URL"] = upstream_base_url
            env["KIMI_MODEL_API_KEY"] = upstream_api_key
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

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
