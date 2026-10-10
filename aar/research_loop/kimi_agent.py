"""Kimi Code CLI adapter for the autonomous research loop."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import signal
import shlex
import shutil
import sqlite3
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


_DEGENERATE_OUTPUT_STOP = "!!!!!!!!!!!!!!!!"


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
    *,
    upstream_origin: str,
    upstream_api_key: str,
    allowed_prefix: str,
    disable_thinking: bool,
    tool_choice_controller: "_ToolChoiceController",
) -> type[BaseHTTPRequestHandler]:
    """Build a loopback handler for request fields absent from Kimi config."""

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
                    if disable_thinking:
                        template_options = payload.setdefault(
                            "chat_template_kwargs", {}
                        )
                        if not isinstance(template_options, dict):
                            raise ValueError("chat_template_kwargs must be an object")
                        template_options["enable_thinking"] = False
                        # Kimi-K2.6 can enter an unbounded `The!!!!...` loop in
                        # non-thinking mode. Preserve the configured maximum
                        # output allowance for legitimate responses while
                        # terminating only this observed degenerate sequence.
                        stop = payload.get("stop")
                        if stop is None:
                            payload["stop"] = [_DEGENERATE_OUTPUT_STOP]
                        elif isinstance(stop, str):
                            payload["stop"] = [stop, _DEGENERATE_OUTPUT_STOP]
                        elif isinstance(stop, list) and all(
                            isinstance(item, str) for item in stop
                        ):
                            if _DEGENERATE_OUTPUT_STOP not in stop:
                                payload["stop"] = [*stop, _DEGENERATE_OUTPUT_STOP]
                        else:
                            raise ValueError("stop must be a string or string array")
                    requested_tool = tool_choice_controller.consume(
                        payload.get("tools")
                    )
                    if requested_tool:
                        payload["tools"] = [
                            tool
                            for tool in payload["tools"]
                            if isinstance(tool, dict)
                            and isinstance(tool.get("function"), dict)
                            and tool["function"].get("name") == requested_tool
                        ]
                        payload["tool_choice"] = "required"
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


class _ToolChoiceController:
    """One-shot required tool selection shared with the request proxy."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: Optional[str] = None

    def arm(self, tool_name: Optional[str]) -> None:
        with self._lock:
            self._pending = tool_name

    def consume(self, tools: Any) -> Optional[str]:
        with self._lock:
            if not self._pending:
                return None
            available: list[str] = []
            if isinstance(tools, list):
                for item in tools:
                    if not isinstance(item, dict):
                        continue
                    function = item.get("function")
                    if not isinstance(function, dict):
                        continue
                    name = function.get("name")
                    if isinstance(name, str):
                        available.append(name)
            requested = self._pending
            matches = [
                name
                for name in available
                if name == requested or name.endswith(f"__{requested}")
            ]
            if not matches:
                if available:
                    raise ValueError(
                        f"required Kimi checkpoint tool {requested!r} is unavailable"
                    )
                return None
            if len(matches) != 1:
                raise ValueError(
                    f"required Kimi checkpoint tool {requested!r} is ambiguous"
                )
            self._pending = None
            return matches[0]


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
        max_continuations: Optional[int] = None,
        disallowed_tools: Optional[list[str]] = None,
        auto_approve: bool = False,
        force_checkpoint_tools: bool = False,
        turn_timeout_seconds: Optional[float] = None,
    ) -> None:
        self.name = name
        self.workspace = Path(workspace)
        self.model = model
        self.cli_path = cli_path
        self.message_callback = message_callback
        self.system_prompt = system_prompt
        self.include_prior_work = include_prior_work
        self.completion_tool = completion_tool
        if max_continuations is None:
            autodata_enabled = os.getenv("AAR_AUTODATA", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            raw_continuations = os.getenv(
                "AAR_KIMI_MAX_CONTINUATIONS",
                "96" if autodata_enabled else "24",
            )
            try:
                max_continuations = int(raw_continuations)
            except ValueError as error:
                raise ValueError(
                    "AAR_KIMI_MAX_CONTINUATIONS must be an integer"
                ) from error
        if max_continuations < 1:
            raise ValueError("Kimi max_continuations must be at least one")
        self.max_continuations = max_continuations
        self.disallowed_tools = disallowed_tools or []
        self.auto_approve = auto_approve
        self.force_checkpoint_tools = force_checkpoint_tools
        if turn_timeout_seconds is None:
            raw_timeout = os.getenv("AAR_KIMI_TURN_TIMEOUT_SECONDS", "3600")
            try:
                turn_timeout_seconds = float(raw_timeout)
            except ValueError as error:
                raise ValueError(
                    "AAR_KIMI_TURN_TIMEOUT_SECONDS must be numeric"
                ) from error
        if turn_timeout_seconds <= 0:
            raise ValueError("Kimi turn timeout must be greater than zero")
        self.turn_timeout_seconds = turn_timeout_seconds

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

        prompt = self._with_previous_failure_feedback(task)
        prompt = self._with_resumable_approved_run(prompt)
        # Proposal markers are intentionally durable across loop sessions.  Bind
        # training actions to a marker mutation from *this* execute call so a
        # pre-marker proposal rejection cannot inherit the previous session's
        # approved run ID and terminal score/failure marker.
        self._proposal_marker_fingerprint_at_start = (
            self._proposal_marker_fingerprint()
        )

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
            with self._request_policy_proxy(env) as tool_choice_controller:
                while True:
                    command = [executable]
                    if self.model:
                        command.extend(["--model", self.model])
                    if continuation_count:
                        command.append("--continue")
                        current_prompt = self._continuation_prompt(output)
                        required_tool = self._continuation_tool(output)
                    else:
                        if agent_file is not None:
                            command.extend(["--agent-file", str(agent_file)])
                        current_prompt = prompt
                        required_tool = None
                    tool_choice_controller.arm(
                        required_tool if self.force_checkpoint_tools else None
                    )
                    command.extend(
                        ["--prompt", current_prompt, "--output-format", "stream-json"]
                    )
                    try:
                        return_code, stderr, new_tool_uses = await self._run_command(
                            command, env, output
                        )
                    except RuntimeError as error:
                        resumable_timeout = (
                            self.completion_tool is not None
                            and str(error).startswith("Kimi Code turn exceeded ")
                        )
                        if not resumable_timeout or (
                            continuation_count >= self.max_continuations
                        ):
                            raise
                        continuation_count += 1
                        print(
                            "[Kimi] timed-out turn terminated; resuming persisted "
                            f"session ({continuation_count}/{self.max_continuations})"
                        )
                        continue
                    iteration_count += new_tool_uses
                    if return_code != 0:
                        detail = stderr or self._event_error(output["raw_messages"])
                        raise RuntimeError(
                            f"Kimi Code exited with status {return_code}: "
                            f"{detail or 'no error detail'}"
                        )
                    # Proposal markers persist across AutonomousAgentLoop sessions.
                    # Only the session that actually submitted the proposal may act
                    # on that marker; otherwise one failed run poisons every later
                    # session and burns the iteration budget without allowing a fix.
                    owns_approved_run = (
                        self._submitted_proposal_in_output(output)
                        and self._proposal_marker_changed_this_session()
                    ) or self._resume_approved_proposal_enabled()
                    production_canary_complete = False
                    if owns_approved_run:
                        approved_run_id = self._approved_run_id()
                        if approved_run_id is not None and (
                            not self._autodata_enabled()
                            or self._autodata_handoff_ready(approved_run_id)
                        ):
                            if self._autodata_stop_after_production():
                                self._complete_autodata_production_canary(
                                    approved_run_id
                                )
                                production_canary_complete = True
                            else:
                                self._ensure_approved_training_submission()
                                await self._wait_for_training_result()
                                training_failure = self._current_training_failure()
                                score_path = self._score_path_for_run(approved_run_id)
                                if training_failure is not None and not (
                                    score_path is not None and score_path.is_file()
                                ):
                                    raise RuntimeError(
                                        "Kimi training failed closed: "
                                        + json.dumps(
                                            training_failure, sort_keys=True
                                        )[:2000]
                                    )
                    if production_canary_complete:
                        break
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
            start_new_session=True,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        stderr_task = asyncio.create_task(process.stderr.read())
        tool_uses = 0

        async def consume_stdout() -> int:
            nonlocal tool_uses
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
            return await process.wait()

        try:
            try:
                return_code = await asyncio.wait_for(
                    consume_stdout(), timeout=self.turn_timeout_seconds
                )
            except TimeoutError as error:
                await self._terminate_process_group(process)
                tool_names = [
                    str(item.get("tool", ""))
                    for item in output.get("tool_uses", [])
                ]
                last_event = output.get("raw_messages", [])[-1:]
                last_event_type = (
                    str(last_event[0].get("type", ""))
                    if last_event and isinstance(last_event[0], dict)
                    else ""
                )
                raise RuntimeError(
                    "Kimi Code turn exceeded "
                    f"{self.turn_timeout_seconds:g} seconds; terminated its "
                    f"process group; tools={tool_names}, "
                    f"last_event_type={last_event_type!r}"
                ) from error
            stderr = (await stderr_task).decode("utf-8", errors="replace").strip()
            if stderr:
                prior = output.get("stderr")
                output["stderr"] = f"{prior}\n{stderr}".strip() if prior else stderr
            return return_code, stderr, tool_uses
        except BaseException:
            await self._terminate_process_group(process)
            if not stderr_task.done():
                stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task
            raise

    @staticmethod
    async def _terminate_process_group(
        process: asyncio.subprocess.Process,
    ) -> None:
        """Terminate the CLI and native-tool descendants from the same turn."""

        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except TimeoutError:
                pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.returncode is None:
            await process.wait()

    def _completion_tool_used(self, output: dict[str, Any]) -> bool:
        expected = self.completion_tool
        used = bool(
            expected
            and any(
                item.get("tool") == expected
                or str(item.get("tool", "")).endswith(f"__{expected}")
                for item in output["tool_uses"]
            )
        )
        if not used or expected != "share_finding":
            return used
        if os.getenv("AAR_REQUIRE_SUCCESSFUL_ITERATIONS", "0").lower() not in {
            "1",
            "true",
            "yes",
        }:
            return True
        run_id = self._approved_run_id()
        if run_id is None:
            return False
        team_dir = os.environ.get("TEAM_DIR", "").strip()
        if not team_dir:
            return False
        safe_run_id = "".join(
            char if (char.isalnum() or char in "_.-") else "_" for char in run_id
        )
        post = Path(team_dir) / ".finding_dedup" / f"runid_{safe_run_id}" / "post.json"
        try:
            persisted = json.loads(post.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        return bool(persisted.get("post_id") or persisted.get("finding_id"))

    @staticmethod
    def _tool_name(item: dict[str, Any]) -> str:
        return str(item.get("tool", "")).rsplit("__", 1)[-1]

    @classmethod
    def _submitted_proposal_in_output(cls, output: dict[str, Any]) -> bool:
        return any(
            cls._tool_name(item) == "submit_idea_proposal"
            for item in output.get("tool_uses", [])
        )

    def _continuation_prompt(self, output: dict[str, Any]) -> str:
        """Require one concrete next milestone instead of replaying the task."""
        if self.completion_tool != "share_finding":
            return (
                "Your previous turn stopped before the required tool call. In this "
                "turn, emit native structured tool calls rather than describing or "
                f"printing them, and call {self.completion_tool}."
            )

        uses = output["tool_uses"]
        names = [self._tool_name(item) for item in uses]
        inputs = [item.get("input") or {} for item in uses]
        if not uses:
            return (
                "Call the native structured MCP tool get_literature exactly once "
                "now with an empty input. Do not emit prose or call another tool."
            )
        recipe_root_raw = os.environ.get("AAR_AUTODATA_RECIPE_ROOT", "").strip()
        recipe_root = Path(recipe_root_raw).resolve() if recipe_root_raw else None
        recipe_files = (
            [
                recipe_root / "autodata.pipeline.json",
                recipe_root / "objective.json",
                recipe_root / "comparator.json",
                recipe_root / "grounding/coverage.json",
                recipe_root / "recipe/generation_strategy.json",
                recipe_root / "recipe/judge_rubric.json",
                recipe_root / "recipe/request.json",
                recipe_root / "recipe/task.py",
            ]
            if recipe_root is not None
            else []
        )
        recipe_context_seen = not recipe_files or any(
            name == "Bash"
            and all(str(path) in input_text for path in recipe_files)
            for name, input_text in (
                (
                    name,
                    str(inputs[index].get("command", "")),
                )
                for index, name in enumerate(names)
            )
        )
        if self._autodata_enabled() and not recipe_context_seen:
            command = "head -n 10000 " + " ".join(
                shlex.quote(str(path)) for path in recipe_files
            )
            return (
                "Call the native Bash tool exactly once now with command="
                f"{json.dumps(command)}. This reads the complete reviewed AutoData "
                "pipeline, objective, comparator, grounding coverage, generation "
                "strategy, judge rubric, request, and task implementation needed "
                "for a reproducible proposal. Do not emit prose or call another tool."
            )
        template_path = (self.workspace / "aar/ideas/TEMPLATE/run.py").resolve()
        idea_name = os.environ.get("IDEA_NAME", "chain")
        chain_id = re.sub(r"[^A-Za-z0-9]+", "_", idea_name).strip("_") or "chain"
        method_module = f"{chain_id}__kimi_candidate"
        ideas_root = Path(os.environ.get("AAR_IDEAS_DIR", "$AAR_IDEAS_DIR"))
        method_dir = ideas_root / method_module
        method_path = method_dir / "run.py"

        def input_text(index: int, key: str) -> str:
            value = inputs[index].get(key, "")
            return value if isinstance(value, str) else str(value)

        template_seen = any(
            name == "Read"
            and input_text(index, "path").endswith("aar/ideas/TEMPLATE/run.py")
            for index, name in enumerate(names)
        )
        scaffold_seen = any(
            name == "Bash"
            and method_module in input_text(index, "command")
            and "TEMPLATE" in input_text(index, "command")
            for index, name in enumerate(names)
        )
        edit_indices = [
            index
            for index, name in enumerate(names)
            if name in {"Write", "Edit"}
            and method_module in input_text(index, "path")
            and input_text(index, "path").endswith("run.py")
        ]
        edit_index = max(edit_indices, default=-1)
        contract_status, contract_errors = self._method_contract_status(method_path)
        proposal_index = max(
            (
                index
                for index, name in enumerate(names)
                if name == "submit_idea_proposal"
                and index > edit_index
            ),
            default=-1,
        )
        approved_run_id = (
            self._approved_run_id()
            if proposal_index >= 0 or self._resume_approved_proposal_enabled()
            else None
        )
        training_job_id = (
            self._current_training_job_id(approved_run_id)
            if approved_run_id is not None
            else None
        )

        if (
            approved_run_id is not None
            and self._autodata_enabled()
            and not self._autodata_handoff_ready(approved_run_id)
        ):
            workspace_id = self._autodata_workspace_id(approved_run_id)
            if workspace_id is not None:
                action = self._autodata_pending_action_record()
                if action is not None and action["kind"] in {
                    "approve_grounding",
                    "approve_baseline",
                    "approve_resources",
                }:
                    return (
                        "Call the native structured MCP tool review_autodata_action "
                        f"exactly once now with action_id={action['id']}. This is a "
                        "delegated approval action; do not begin, complete, or approve "
                        "it through Bash and do not emit prose."
                    )
                if action is not None:
                    if action["status"] == "pending":
                        self._autodata_begin_action(action)
                        action = self._autodata_action_record(action["id"])
                    if action is None or action["status"] != "in_progress":
                        raise RuntimeError(
                            "trusted AutoData action bridge failed to acquire action"
                        )
                    result_path = Path(
                        f"/tmp/aar-autodata-{action['id']}-result.json"
                    )
                    requires_pipeline_edit = (
                        self._autodata_pipeline_feedback_requires_edit(action)
                    )
                    if result_path.is_file() and requires_pipeline_edit:
                        # A result that claims a pipeline revision before the sole
                        # mutable strategy actually changed is not evidence of work.
                        result_path.unlink()
                    if not result_path.is_file():
                        self._autodata_prepare_editable_paths(action)
                        action_spec = json.dumps(action.get("spec"), sort_keys=True)[:6000]
                        editable_context = self._autodata_editable_context(action)
                        if requires_pipeline_edit:
                            strategy_path = (
                                Path(action["spec"]["editable_root"])
                                / "recipe"
                                / "generation_strategy.json"
                            )
                            return (
                                "The trusted controller has securely leased native "
                                f"AutoData action {action['id']}; do not call action "
                                "begin, action complete, or status. The native review "
                                "requires a real pipeline revision, but the mutable "
                                "generation strategy is still byte-identical to the "
                                "reviewed baseline. Call the native Write tool exactly "
                                f"once now with path={json.dumps(str(strategy_path))} "
                                "and full replacement JSON that preserves the existing "
                                "schema and keys while addressing the action feedback. "
                                "Do not write the action-result file yet and do not use "
                                "Bash. Action specification: "
                                f"{action_spec}. Current allowed-file content: "
                                f"{editable_context}"
                            )
                        return (
                            "The trusted controller has securely leased native AutoData "
                            f"action {action['id']}; do not call action begin, action "
                            "complete, or status. Call the native Write tool exactly "
                            "once now. If the action still requires one scoped allowed "
                            "file edit, make that edit under editable_root first. Treat "
                            "the current allowed-file content below as authoritative: "
                            "preserve every existing key, nested setting, and value type "
                            "unless the action explicitly requires changing it. Never "
                            "replace a compiled file with a smaller invented schema. "
                            "When complete reviewed files are already staged and satisfy "
                            "the action, adopt them unchanged and write the action-result "
                            "JSON immediately instead of rewriting them. "
                            "Otherwise write a valid JSON object to "
                            f"{result_path} satisfying the requested outputs. Use only "
                            "the action instructions and allowed paths; do not use Bash. "
                            f"Action specification: {action_spec}. "
                            f"Current allowed-file content: {editable_context}"
                        )
                    self._autodata_complete_action(action["id"], result_path)
                status_subject = self._autodata_status_subject(workspace_id)
                status_snapshot = self._autodata_native_status(status_subject)
                status_command = (
                    "sleep 10"
                )
                return (
                    f"The proposal is approved with run_id={approved_run_id}, and "
                    "trusted orchestration already created and registered native "
                    f"AutoData workspace_id={workspace_id}. The current supervised "
                    f"status subject is {status_subject}. Trusted read-only native "
                    "status is "
                    f"{json.dumps(status_snapshot, sort_keys=True)[:12000]}. "
                    "Do not load a skill, "
                    "create/fork/register a workspace, edit the approved method, or "
                    "submit another proposal. If the status is still active with no "
                    "pending host action, the lifecycle supervisor owns the next "
                    "deterministic step: call the native Bash tool exactly once now "
                    f"with command={json.dumps(status_command)} and do not run a "
                    "lifecycle or status command yourself. If the status is terminal, "
                    "use the system prompt's exact next non-action export or supervised "
                    "execution-creation command instead. Continue until the verified "
                    "training handoff exists."
                )
            return (
                f"The proposal is already approved with run_id={approved_run_id}. "
                "Do not submit training, change the approved method, or submit "
                "another proposal. Continue the required native AutoData workflow "
                "now. Trusted orchestration must create and register the run-scoped "
                "workspace; do not attempt that bootstrap manually. Obtain only the "
                "delegated native approvals, complete meta-optimization and the "
                "dedicated production execution, then write the verified "
                f"$TEAM_DIR/autodata/{approved_run_id}/training-handoff.json. "
                "Use concrete native tool calls; approval alone is not completion."
            )

        if training_job_id is not None:
            score_path = self._score_path_for_run(approved_run_id)
            score_read = score_path is not None and any(
                name == "Read"
                and Path(input_text(index, "path")) == score_path
                for index, name in enumerate(names)
            )
            if score_path is not None and score_path.is_file() and score_read:
                return (
                    "Call the native structured MCP tool share_finding exactly once "
                    "now, using the approved run_id and the real score you already "
                    "read. Include a results_writeup of at least 80 characters that "
                    "explains which public benchmarks moved, capability behavior, "
                    "mechanism, and limitations. Do not emit prose or call "
                    "evaluate_model."
                )
            if score_path is not None and score_path.is_file():
                return (
                    "Call the native Read tool exactly once now with path="
                    f"{json.dumps(str(score_path))}. Do not emit prose or another tool."
                )
            return (
                "Call the native Bash tool exactly once now. Do not resubmit training. "
                f"foreground-poll Slurm job {training_job_id} until "
                f"$SCORES_DIR/{approved_run_id}.json or "
                f"{approved_run_id}.failed.json exists, then print that file. Do not "
                "emit prose."
            )
        if proposal_index >= 0:
            approved = (
                self._proposal_is_approved()
                if self._proposal_marker_changed_this_session()
                else False
            )
            if approved is True and approved_run_id is not None:
                submitter = self.workspace / "scripts/submit_train_job.sh"
                run_id_q = shlex.quote(approved_run_id)
                module_q = shlex.quote(method_module)
                submitter_q = shlex.quote(str(submitter))
                command = (
                    f"RUN_ID={run_id_q}; printf '%s\\n' \"$RUN_ID\" > "
                    "/tmp/run_id_current; "
                    f"jobid=$(bash {submitter_q} {module_q} \"$RUN_ID\"); "
                    "case \"$jobid\" in ''|*[!0-9]*) echo 'invalid Slurm job id' "
                    " >&2; exit 2;; esac; printf '%s\\n' \"$jobid\" > "
                    '"/tmp/jobid_$RUN_ID"; printf \'%s\\n\' "$jobid"'
                )
                return (
                    "Call the native Bash tool exactly once now with command="
                    f"{json.dumps(command)}. This exact idempotent command submits the "
                    "approved run and persists its verified Slurm receipt. Do not alter "
                    "the command, emit prose, or call another tool."
                )
            if approved is False:
                if self._proposal_rejection_is_paper_only(method_path):
                    return (
                        "Call the native structured MCP tool submit_idea_proposal "
                        "exactly once now for the same implemented method, revising "
                        "only the mini-paper fields to incorporate every "
                        "missing_for_reproduction item from the monitor result. Keep "
                        "the code unchanged and make its actual loss masking, exact "
                        "reviewed AutoData recipe/rubric thresholds, generation "
                        "strategy, and meta-optimization procedure reproducible. Do "
                        "not emit prose or another tool."
                    )
                return (
                    "Call the native Write tool exactly once now with path="
                    f"{json.dumps(str(method_path))} and full replacement content that "
                    "revises this canonical candidate from the submit_idea_proposal "
                    "monitor feedback. Do not create or write another candidate "
                    "directory, emit prose, or call another tool."
                )
            return (
                "Inspect the actual submit_idea_proposal result. If it is approved, "
                "use its run_id exactly. If rejected, revise the same run.py from the "
                "monitor feedback. Do not invent a run id or emit prose."
            )
        if edit_index >= 0 and contract_status == "passed":
            return (
                "Call the native structured MCP tool submit_idea_proposal exactly once "
                f"now for the implemented method {method_module}. Fill every required "
                "method-paper and compliance field from the code and literature. Do "
                "not emit prose or another tool."
            )
        if edit_index >= 0:
            if contract_status == "failed":
                error_summary = "; ".join(contract_errors)[:4000]
                return (
                    "Call the native Write tool exactly once now with path="
                    f"{json.dumps(str(method_path))} and full replacement content that "
                    "fixes every method-contract error while preserving the intended "
                    "research method and the copied scaffold's MethodConfig, dry_run, "
                    "smoke_run, and run_experiment interface. "
                    f"Errors: {json.dumps(error_summary)}. Do not emit prose or another "
                    "tool."
                )
            validator = self.workspace / "scripts/validate_method_contract.py"
            proof = method_dir / ".aar-method-contract.json"
            command = (
                f"timeout 60s python {validator} {method_path} --proof {proof} "
                "--run-dry-run"
            )
            if os.environ.get("AAR_REQUIRE_GEMMA4_TARGETS") == "1":
                command += " --require-gemma4-targets"
            if os.environ.get("AAR_REQUIRE_METHOD_SMOKE") == "1":
                command += " --require-smoke-run"
            if self._autodata_enabled():
                command += " --require-autodata-loader"
            return (
                "Call the native Bash tool exactly once now with command="
                f"{json.dumps(command)} to validate the complete import, MethodConfig, "
                "run_experiment, and phase contract. Do not emit prose or another tool."
            )
        if scaffold_seen:
            return (
                "Call the native Write tool exactly once now with path="
                f"{json.dumps(str(method_path))} and full replacement content for a "
                "concrete, compliant multidimensional training method based on the "
                "template and literature already read. Preserve the copied scaffold's "
                "MethodConfig, dry_run and one-step real-GPU smoke_run behavior, load "
                "helper, and run_experiment "
                "interface; include all five required phase contexts. Do not emit prose "
                "or another tool."
            )
        if template_seen:
            command = (
                f"mkdir -p {method_dir} && "
                f"cp -a {self.workspace / 'aar/ideas/TEMPLATE'}/. {method_dir}/"
            )
            return (
                "Call the native Bash tool exactly once now with command="
                f"{json.dumps(command)}. This creates the candidate scaffold. Do not "
                "emit prose or another tool."
            )
        return (
            "Call the native Read tool exactly once now with path="
            f"{json.dumps(str(template_path))}. Do not call literature, emit prose, "
            "or call another tool."
        )

    def _continuation_tool(self, output: dict[str, Any]) -> Optional[str]:
        """Return the one tool required by the current fail-closed checkpoint."""
        if self.completion_tool != "share_finding":
            return self.completion_tool
        prompt = self._continuation_prompt(output)
        if "MCP tool share_finding exactly once" in prompt:
            return "share_finding"
        if "MCP tool submit_idea_proposal exactly once" in prompt:
            return "submit_idea_proposal"
        if "MCP tool get_literature exactly once" in prompt:
            return "get_literature"
        if "MCP tool review_autodata_action exactly once" in prompt:
            return "review_autodata_action"
        if "native Read tool exactly once" in prompt:
            return "Read"
        if "native Write tool exactly once" in prompt:
            return "Write"
        if "native Bash tool exactly once" in prompt:
            return "Bash"
        return None

    @staticmethod
    def _autodata_action_record(action_id: str) -> dict[str, Any] | None:
        """Read non-secret action state needed to resume a leased host action."""
        if not re.fullmatch(r"act_[0-9a-f]{24}", action_id):
            return None
        state_raw = os.environ.get("AAR_AUTODATA_STATE", "").strip()
        if not state_raw:
            return None
        state = Path(state_raw)
        if state.is_symlink() or not state.is_file():
            return None
        try:
            with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
                row = connection.execute(
                    "SELECT kind,status,specJson FROM actions WHERE id=?",
                    (action_id,),
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        try:
            spec = json.loads(str(row[2]))
        except json.JSONDecodeError:
            return None
        if not isinstance(spec, dict):
            return None
        return {
            "id": action_id,
            "kind": str(row[0]),
            "status": str(row[1]),
            "spec": spec,
        }

    @staticmethod
    def _autodata_pending_action_record() -> dict[str, Any] | None:
        state_raw = os.environ.get("AAR_AUTODATA_STATE", "").strip()
        if not state_raw:
            return None
        state = Path(state_raw)
        if state.is_symlink() or not state.is_file():
            return None
        try:
            with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
                row = connection.execute(
                    "SELECT id FROM actions WHERE status IN ('pending','in_progress') "
                    "ORDER BY createdAt,id LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        return KimiAgent._autodata_action_record(str(row[0]))

    @staticmethod
    def _autodata_cli(*arguments: str) -> dict[str, Any]:
        plugin_raw = os.environ.get("AAR_AUTODATA_PLUGIN_ROOT", "").strip()
        state = os.environ.get("AAR_AUTODATA_STATE", "").strip()
        artifacts = os.environ.get("AAR_AUTODATA_ARTIFACTS", "").strip()
        workspaces = os.environ.get("AAR_AUTODATA_WORKSPACES", "").strip()
        if not all((plugin_raw, state, artifacts, workspaces)):
            raise RuntimeError("trusted AutoData action bridge is not configured")
        wrapper = Path(plugin_raw) / "scripts/autodata.py"
        if wrapper.is_symlink() or not wrapper.is_file():
            raise RuntimeError("trusted AutoData wrapper is unavailable")
        python = os.environ.get("AAR_AUTODATA_WRAPPER_PYTHON", sys.executable)
        completed = subprocess.run(
            [
                python,
                str(wrapper),
                "--state",
                state,
                "--artifacts",
                artifacts,
                "--workspaces",
                workspaces,
                *arguments,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip()[-2000:]
            raise RuntimeError(
                "trusted AutoData action bridge command failed: "
                + (detail or f"exit {completed.returncode}")
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "trusted AutoData action bridge returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise RuntimeError("trusted AutoData action bridge returned a non-object")
        return payload

    @staticmethod
    def _autodata_action_lease_path(action_id: str) -> Path:
        team_raw = os.environ.get("TEAM_DIR", "").strip()
        if not team_raw:
            raise RuntimeError("TEAM_DIR is required for AutoData action leases")
        job_id = re.sub(
            r"[^A-Za-z0-9_.-]", "_", os.environ.get("SLURM_JOB_ID", "local")
        )
        root = Path(team_raw) / "autodata" / "runtime" / job_id / "action-leases"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root / f"{action_id}.token"

    @staticmethod
    def _autodata_action_snapshot_path(action_id: str) -> Path:
        team_raw = os.environ.get("TEAM_DIR", "").strip()
        if not team_raw:
            raise RuntimeError("TEAM_DIR is required for AutoData action snapshots")
        safe_action_id = re.sub(r"[^A-Za-z0-9_.-]", "_", action_id)
        root = Path(team_raw) / "autodata" / "action-snapshots"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root / f"{safe_action_id}.generation-strategy.sha256"

    @staticmethod
    def _write_private_text(path: Path, value: str) -> None:
        temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _autodata_begin_action(cls, action: dict[str, Any]) -> None:
        action_id = action.get("id")
        if not isinstance(action_id, str):
            raise RuntimeError("trusted AutoData action has no identifier")
        lease_path = cls._autodata_action_lease_path(action_id)
        lease_path.unlink(missing_ok=True)
        payload = cls._autodata_cli("action", "begin", action_id)
        token = payload.get("lease_token")
        leased_action = payload.get("action")
        if not isinstance(token, str) or len(token) < 20:
            raise RuntimeError("trusted AutoData action begin returned no lease")
        if not isinstance(leased_action, dict) or leased_action.get("id") != action_id:
            raise RuntimeError("trusted AutoData action begin returned the wrong action")
        # The begin response may intentionally be compact.  Capture from the
        # complete pre-begin SQLite record supplied by the trusted caller.
        cls._autodata_capture_pipeline_revision_baseline(action)
        cls._write_private_text(lease_path, token)

    @classmethod
    def _autodata_complete_action(cls, action_id: str, result_path: Path) -> None:
        try:
            result = json.loads(result_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("AutoData action result is not valid JSON") from error
        if not isinstance(result, dict):
            raise RuntimeError("AutoData action result must be one JSON object")
        lease_path = cls._autodata_action_lease_path(action_id)
        try:
            token = lease_path.read_text().strip()
        except OSError as error:
            raise RuntimeError("trusted AutoData action lease is unavailable") from error
        if len(token) < 20:
            raise RuntimeError("trusted AutoData action lease is invalid")
        action = cls._autodata_action_record(action_id)
        if action is not None and action["kind"] == "author_grounding":
            cls._autodata_repair_incomplete_grounding(action)
        cls._autodata_cli(
            "action",
            "complete",
            action_id,
            "--lease-token",
            token,
            "--result",
            str(result_path),
        )
        lease_path.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)

        if action is not None:
            cls._autodata_action_snapshot_path(action_id).unlink(missing_ok=True)

    @classmethod
    def _autodata_capture_pipeline_revision_baseline(
        cls, action: dict[str, Any]
    ) -> None:
        """Persist the pre-action strategy digest across researcher retries."""
        if not cls._autodata_pipeline_has_feedback(action):
            return
        spec = action.get("spec")
        assert isinstance(spec, dict)
        root_raw = spec.get("editable_root")
        if not isinstance(root_raw, str):
            raise RuntimeError("AutoData pipeline revision has no editable root")
        strategy = (
            Path(root_raw).resolve(strict=True)
            / "recipe"
            / "generation_strategy.json"
        )
        if strategy.is_symlink() or not strategy.is_file():
            raise RuntimeError("AutoData generation strategy is unavailable")
        snapshot = cls._autodata_action_snapshot_path(str(action["id"]))
        if not snapshot.is_file():
            cls._write_private_text(snapshot, hashlib.sha256(strategy.read_bytes()).hexdigest())

    @staticmethod
    def _autodata_pipeline_has_feedback(action: dict[str, Any]) -> bool:
        if action.get("kind") != "author_pipeline":
            return False
        spec = action.get("spec")
        if not isinstance(spec, dict):
            return False
        instructions = spec.get("instructions")
        scope = spec.get("scope")
        revision = scope.get("revision") if isinstance(scope, dict) else None
        # Revision 3 is the first pipeline-authoring action; its "Latest
        # feedback" is the approved grounding review and does not require a
        # strategy mutation.  A later pipeline action is a concrete rework
        # request after the native dry-run/baseline review.
        return (
            isinstance(instructions, str)
            and "Latest feedback:" in instructions
            and isinstance(revision, int)
            and revision > 3
        )

    @classmethod
    def _autodata_pipeline_feedback_requires_edit(cls, action: dict[str, Any]) -> bool:
        """Require a real strategy mutation before accepting revision narration."""
        if not cls._autodata_pipeline_has_feedback(action):
            return False
        spec = action["spec"]
        root_raw = spec.get("editable_root")
        action_id = action.get("id")
        if not isinstance(root_raw, str) or not isinstance(action_id, str):
            return True
        try:
            current = (
                Path(root_raw).resolve(strict=True)
                / "recipe"
                / "generation_strategy.json"
            )
            snapshot = cls._autodata_action_snapshot_path(action_id)
            if current.is_symlink() or snapshot.is_symlink():
                return True
            expected = snapshot.read_text(encoding="utf-8").strip()
            actual = hashlib.sha256(current.read_bytes()).hexdigest()
            return not expected or actual == expected
        except OSError:
            return True

    @staticmethod
    def _autodata_repair_incomplete_grounding(action: dict[str, Any]) -> None:
        """Restore reviewed grounding when a host edit discarded its task corpus."""
        spec = action.get("spec")
        if not isinstance(spec, dict):
            raise RuntimeError("AutoData grounding action has no specification")
        root_raw = spec.get("editable_root")
        allowed = spec.get("allowed_paths")
        if not isinstance(root_raw, str) or allowed != ["grounding/**"]:
            raise RuntimeError("AutoData grounding action has an unexpected edit scope")
        root = Path(root_raw).resolve(strict=True)
        grounding = root / "grounding"
        if grounding.is_symlink():
            raise RuntimeError("AutoData grounding directory must not be a symlink")
        grounding.mkdir(parents=True, exist_ok=True, mode=0o700)
        if grounding.resolve(strict=True).parent != root:
            raise RuntimeError("AutoData grounding directory escaped the editable root")
        manifest = grounding / "manifest.json"
        if manifest.is_symlink():
            raise RuntimeError("AutoData grounding manifest must not be a symlink")
        partition_counts = [
            int(os.environ[name])
            for name in (
                "AAR_AUTODATA_TUNING_TASKS",
                "AAR_AUTODATA_VALIDATION_TASKS",
                "AAR_AUTODATA_TEST_TASKS",
            )
        ]
        if min(partition_counts) < 1:
            raise RuntimeError("AutoData grounding partitions must all be non-empty")
        required_count = sum(partition_counts)

        try:
            current = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            current = None
        tasks = current.get("tasks") if isinstance(current, dict) else None
        if (
            isinstance(current, dict)
            and current.get("schema") == "autodata.grounding/v1"
            and isinstance(tasks, list)
            and len(tasks) == required_count
            and all(
                isinstance(task, dict)
                and isinstance(task.get("id"), str)
                and task["id"].strip()
                for task in tasks
            )
        ):
            return

        recipe_raw = os.environ.get("AAR_AUTODATA_RECIPE_ROOT", "").strip()
        if not recipe_raw:
            raise RuntimeError("reviewed AutoData recipe root is unavailable")
        recipe = Path(recipe_raw).resolve(strict=True)
        builder = recipe / "grounding" / "build_manifest.py"
        coverage = recipe / "grounding" / "coverage.json"
        if (
            builder.is_symlink()
            or coverage.is_symlink()
            or not builder.is_file()
            or not coverage.is_file()
        ):
            raise RuntimeError("reviewed AutoData grounding sources are unavailable")
        shutil.copy2(builder, grounding / "build_manifest.py")
        shutil.copy2(coverage, grounding / "coverage.json")
        completed = subprocess.run(
            [
                sys.executable,
                str(builder),
                "--count",
                str(required_count),
                "--coverage",
                str(coverage),
                "--output",
                str(manifest),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr[-2000:].strip() or completed.stdout[-2000:].strip()
            raise RuntimeError(f"reviewed grounding repair failed: {detail}")
        try:
            repaired = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("reviewed grounding repair returned invalid JSON") from error
        repaired_tasks = repaired.get("tasks") if isinstance(repaired, dict) else None
        if (
            not isinstance(repaired, dict)
            or repaired.get("schema") != "autodata.grounding/v1"
            or not isinstance(repaired_tasks, list)
            or len(repaired_tasks) != required_count
        ):
            raise RuntimeError("reviewed grounding repair returned an invalid manifest")

    @staticmethod
    def _autodata_editable_context(action: dict[str, Any]) -> str:
        """Return bounded, path-safe context for a leased action's editable files."""
        spec = action.get("spec")
        if not isinstance(spec, dict):
            return "{}"
        root_raw = spec.get("editable_root")
        allowed = spec.get("allowed_paths")
        if not isinstance(root_raw, str) or not isinstance(allowed, list):
            return "{}"
        try:
            root = Path(root_raw).resolve(strict=True)
        except OSError:
            return "{}"
        remaining = 20_000
        context: dict[str, str] = {}
        for relative_raw in allowed:
            if remaining <= 0 or not isinstance(relative_raw, str):
                break
            wildcard = relative_raw == "**" or relative_raw.endswith("/**")
            relative = Path(".") if relative_raw == "**" else Path(
                relative_raw[:-3] if wildcard else relative_raw
            )
            if relative.is_absolute() or ".." in relative.parts:
                continue
            candidate = root / relative
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, ValueError):
                context[relative_raw] = "<missing>"
                continue
            if wildcard and resolved.is_dir() and not candidate.is_symlink():
                priority = {
                    "recipe/generation_strategy.json": 0,
                    "autodata.pipeline.json": 1,
                    "objective.json": 2,
                    "comparator.json": 3,
                    "recipe/request.json": 4,
                    "recipe/judge_rubric.json": 5,
                    "framework.lock.json": 6,
                    "grounding/manifest.json": 7,
                }
                files = sorted(
                    (
                        path
                        for path in resolved.rglob("*")
                        if path.is_file()
                        and not path.is_symlink()
                        and "approval" not in path.relative_to(root).parts
                    ),
                    key=lambda path: (
                        priority.get(str(path.relative_to(root)), 20),
                        str(path.relative_to(root)),
                    ),
                )[:32]
                for path in files:
                    if remaining <= 0:
                        break
                    try:
                        safe = path.resolve(strict=True)
                        safe.relative_to(root)
                        content = safe.read_text(encoding="utf-8")
                    except (OSError, UnicodeError, ValueError):
                        continue
                    key = str(safe.relative_to(root))
                    excerpt = content[: min(12_000, remaining)]
                    suffix = (
                        ""
                        if len(excerpt) == len(content)
                        else f"\n<TRUNCATED bytes={len(content)} "
                        f"sha256={hashlib.sha256(content.encode()).hexdigest()}>"
                    )
                    context[key] = excerpt + suffix
                    remaining -= len(excerpt)
                if not files:
                    context[relative_raw] = "<empty-directory>"
                continue
            if candidate.is_symlink() or not resolved.is_file():
                context[relative_raw] = "<unsafe-or-not-a-file>"
                continue
            try:
                content = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                context[relative_raw] = "<unreadable>"
                continue
            excerpt = content[:remaining]
            context[relative_raw] = excerpt
            remaining -= len(excerpt)
        return json.dumps(context, sort_keys=True)

    @staticmethod
    def _autodata_prepare_editable_paths(action: dict[str, Any]) -> None:
        """Create only allowed parent directories needed by structured Write."""
        spec = action.get("spec")
        if not isinstance(spec, dict):
            return
        root_raw = spec.get("editable_root")
        allowed = spec.get("allowed_paths")
        if not isinstance(root_raw, str) or not isinstance(allowed, list):
            return
        try:
            root = Path(root_raw).resolve(strict=True)
        except OSError:
            return
        for relative_raw in allowed:
            if not isinstance(relative_raw, str):
                continue
            wildcard = relative_raw == "**" or relative_raw.endswith("/**")
            relative = Path(".") if relative_raw == "**" else Path(
                relative_raw[:-3] if wildcard else relative_raw
            )
            if relative.is_absolute() or ".." in relative.parts:
                continue
            parent = root / relative if wildcard else (root / relative).parent
            try:
                resolved = parent.resolve(strict=False)
                resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    @classmethod
    def _autodata_native_status(cls, subject_id: str) -> dict[str, Any]:
        return cls._autodata_cli("status", subject_id)

    @staticmethod
    def _autodata_status_subject(workspace_id: str) -> str:
        """Return the newest supervised native subject, falling back to workspace."""
        control_raw = os.environ.get("AAR_AUTODATA_SUPERVISOR_CONTROL", "").strip()
        if not control_raw:
            return workspace_id
        try:
            control = json.loads(Path(control_raw).read_text())
        except (OSError, json.JSONDecodeError):
            return workspace_id
        subjects = control.get("subjects") if isinstance(control, dict) else None
        if not isinstance(subjects, list):
            return workspace_id
        for entry in reversed(subjects):
            if not isinstance(entry, dict) or entry.get("status") != "registered":
                continue
            subject_id = entry.get("subject_id")
            kind = entry.get("kind")
            if not isinstance(subject_id, str):
                continue
            if kind == "workspace" and re.fullmatch(r"ws_[0-9a-f]{32}", subject_id):
                return subject_id
            if kind == "execution" and re.fullmatch(
                r"exe_[0-9a-f]{32}", subject_id
            ):
                return subject_id
        return workspace_id

    @staticmethod
    def _method_contract_status(method_path: Path) -> tuple[Optional[str], list[str]]:
        proof_path = method_path.parent / ".aar-method-contract.json"
        try:
            source_hash = hashlib.sha256(method_path.read_bytes()).hexdigest()
            proof = json.loads(proof_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None, []
        if proof.get("source_sha256") != source_hash:
            return None, []
        status = proof.get("status")
        errors = proof.get("errors")
        if status not in {"passed", "failed"} or not isinstance(errors, list):
            return None, []
        requirements = proof.get("requirements")
        expected_requirements = {
            "require_gemma4_targets": os.environ.get(
                "AAR_REQUIRE_GEMMA4_TARGETS", "0"
            )
            == "1",
            "require_smoke_run": os.environ.get("AAR_REQUIRE_METHOD_SMOKE", "0")
            == "1",
            "require_autodata_loader": KimiAgent._autodata_enabled(),
        }
        missing = [
            name
            for name, required in expected_requirements.items()
            if required
            and (
                not isinstance(requirements, dict)
                or requirements.get(name) is not True
            )
        ]
        if missing:
            return (
                "failed",
                [
                    "method-contract proof omitted required validation gate(s): "
                    + ", ".join(missing)
                    + "; run the exact trusted validator command without removing "
                    "flags"
                ],
            )
        return status, [str(error) for error in errors]

    @staticmethod
    def _proposal_is_approved() -> Optional[bool]:
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        idea_uid = os.environ.get("IDEA_UID") or os.environ.get("IDEA_NAME")
        if not scores_dir or not idea_uid:
            return None
        marker = Path(scores_dir) / ".proposals" / f"{idea_uid}.json"
        try:
            payload = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        approved = payload.get("approved")
        return approved if isinstance(approved, bool) else None

    @staticmethod
    def _proposal_rejection_is_paper_only(method_path: Path) -> bool:
        """Return true when unchanged code needs only a reproducibility rewrite."""
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        idea_uid = os.environ.get("IDEA_UID") or os.environ.get("IDEA_NAME")
        if not scores_dir or not idea_uid:
            return False
        marker = Path(scores_dir) / ".proposals" / f"{idea_uid}.json"
        try:
            payload = json.loads(marker.read_text())
            source_hash = hashlib.sha256(method_path.read_bytes()).hexdigest()
        except (OSError, json.JSONDecodeError):
            return False
        if payload.get("approved") is not False or payload.get("code_hash") != source_hash:
            return False
        verdict = payload.get("verdict")
        if not isinstance(verdict, dict):
            return False
        if verdict.get("code_diverges_from_proposal") is not False:
            return False
        if verdict.get("reproducible_from_paper") is not False:
            return False
        missing = verdict.get("missing_for_reproduction")
        return isinstance(missing, list) and bool(missing)

    @staticmethod
    def _proposal_marker_fingerprint() -> Optional[str]:
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        idea_uid = os.environ.get("IDEA_UID") or os.environ.get("IDEA_NAME")
        if not scores_dir or not idea_uid:
            return None
        marker = Path(scores_dir) / ".proposals" / f"{idea_uid}.json"
        try:
            return hashlib.sha256(marker.read_bytes()).hexdigest()
        except OSError:
            return None

    def _proposal_marker_changed_this_session(self) -> bool:
        return self._proposal_marker_fingerprint() != getattr(
            self, "_proposal_marker_fingerprint_at_start", None
        )

    @staticmethod
    def _approved_run_id() -> Optional[str]:
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        idea_uid = os.environ.get("IDEA_UID") or os.environ.get("IDEA_NAME")
        if not scores_dir or not idea_uid:
            return None
        marker_path = Path(scores_dir) / ".proposals" / f"{idea_uid}.json"
        try:
            marker = json.loads(marker_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if marker.get("approved") is not True:
            return None
        idea_name = marker.get("idea_name")
        code_hash = marker.get("code_hash")
        candidates: list[tuple[float, str]] = []
        for path in (marker_path.parent / "runs").glob("*.json"):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            run_id = payload.get("run_id")
            if (
                payload.get("idea_name") == idea_name
                and payload.get("code_hash") == code_hash
                and isinstance(run_id, str)
                and re.fullmatch(r"[A-Za-z0-9._-]+", run_id)
                and run_id.startswith(f"{idea_uid}-")
            ):
                candidates.append((float(payload.get("stamped_ts", 0)), run_id))
        return max(candidates, default=(0.0, None))[1]

    @staticmethod
    def _current_training_job_id(run_id: str) -> Optional[str]:
        team_dir = os.environ.get("TEAM_DIR", "").strip()
        if not team_dir:
            return None
        receipt = Path(team_dir) / ".train_submissions" / f"{run_id}.env"
        try:
            values = dict(
                line.split("=", 1)
                for line in receipt.read_text().splitlines()
                if "=" in line
            )
        except OSError:
            return None
        job_id = values.get("job_id", "")
        if values.get("run_id") != run_id or not re.fullmatch(r"[0-9]+", job_id):
            return None
        return job_id

    def _ensure_approved_training_submission(self) -> None:
        """Submit approved work deterministically; never delegate shell quoting to Kimi."""
        if (
            self.completion_tool != "share_finding"
            or os.environ.get("AAR_REQUIRE_TRAIN_RECEIPT") != "1"
        ):
            return
        run_id = self._approved_run_id()
        if run_id is None or self._current_training_job_id(run_id) is not None:
            return
        if self._autodata_enabled() and not self._autodata_handoff_ready(run_id):
            # AutoData work is intentionally forbidden before proposal approval.
            # Therefore an approved proposal cannot be submitted for training until
            # its production lineage has produced the run-scoped handoff.  The
            # continuation loop drives Kimi through that workflow first.
            return
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        idea_uid = os.environ.get("IDEA_UID") or os.environ.get("IDEA_NAME")
        if not scores_dir or not idea_uid:
            return
        marker = Path(scores_dir) / ".proposals" / f"{idea_uid}.json"
        try:
            payload = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError):
            return
        idea_name = payload.get("idea_name")
        if not isinstance(idea_name, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", idea_name
        ):
            raise RuntimeError("approved proposal has an unsafe method module name")
        command = [
            "bash",
            str(self.workspace / "scripts/submit_train_job.sh"),
            idea_name,
            run_id,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace,
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("approved training submission timed out") from error
        job_id = completed.stdout.strip()
        if completed.returncode != 0 or not re.fullmatch(r"[0-9]+", job_id):
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                "approved training submission failed: " + detail[-4000:]
            )
        receipt_job = self._current_training_job_id(run_id)
        if receipt_job != job_id:
            raise RuntimeError("training submission did not publish its verified receipt")
        print(f"[Kimi] deterministically submitted approved training job {job_id}")

    @staticmethod
    def _autodata_enabled() -> bool:
        return os.getenv("AAR_AUTODATA", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _autodata_stop_after_production() -> bool:
        return os.getenv("AAR_AUTODATA_STOP_AFTER", "").strip() == "production"

    @classmethod
    def _complete_autodata_production_canary(cls, run_id: str) -> Path:
        """Verify and durably mark a production-only AutoData canary."""
        if not cls._autodata_stop_after_production():
            raise RuntimeError("AutoData production-only stop is not active")
        team_raw = os.getenv("TEAM_DIR", "").strip()
        if not team_raw:
            raise RuntimeError("TEAM_DIR is required for the production canary")
        try:
            required_rows = int(os.environ["AAR_AUTODATA_PRODUCTION_ROWS"])
        except (KeyError, ValueError) as error:
            raise RuntimeError(
                "AAR_AUTODATA_PRODUCTION_ROWS must be an integer"
            ) from error
        from aar.infrastructure.autodata_lifecycle import verify_preflight

        verification = verify_preflight(run_id)
        if verification.get("available_rows", 0) < required_rows:
            raise RuntimeError(
                "verified production handoff did not satisfy the configured row target"
            )
        marker = (
            Path(team_raw)
            / "autodata"
            / run_id
            / "production-canary-complete.json"
        )
        payload = {
            "schema": "aar.autodata.production-canary-complete/v1",
            "run_id": run_id,
            "stop_after": "production",
            "required_accepted_rows": required_rows,
            "verification": verification,
        }
        encoded = json.dumps(payload, indent=2, sort_keys=True)
        if marker.exists():
            try:
                existing = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError(
                    "existing production-canary marker is unreadable"
                ) from error
            if existing != payload:
                raise RuntimeError(
                    "existing production-canary marker does not match verification"
                )
        else:
            cls._write_private_text(marker, encoded)
        print(
            "[Kimi] verified AutoData production canary: "
            f"{verification['available_rows']} accepted rows; stopping before training"
        )
        return marker

    @staticmethod
    def _resume_approved_proposal_enabled() -> bool:
        return os.getenv("AAR_RESUME_APPROVED_PROPOSAL", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _autodata_handoff_ready(run_id: str) -> bool:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
            return False
        team_dir = os.getenv("TEAM_DIR", "").strip()
        if not team_dir:
            return False
        return (
            Path(team_dir) / "autodata" / run_id / "training-handoff.json"
        ).is_file()

    @staticmethod
    def _autodata_workspace_id(run_id: str) -> str | None:
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", run_id):
            return None
        team_dir = os.getenv("TEAM_DIR", "").strip()
        if not team_dir:
            return None
        path = (
            Path(team_dir)
            / "autodata"
            / run_id
            / "workspace-bootstrap.json"
        )
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        workspace_id = value.get("workspace_id")
        if isinstance(workspace_id, str) and re.fullmatch(
            r"ws_[0-9a-f]{32}", workspace_id
        ):
            return workspace_id
        return None

    def _with_resumable_approved_run(self, task: str) -> str:
        if not self._resume_approved_proposal_enabled():
            return task
        run_id = self._approved_run_id()
        if run_id is None:
            return task
        if self._autodata_enabled() and not self._autodata_handoff_ready(run_id):
            workspace_id = self._autodata_workspace_id(run_id)
            return (
                task
                + "\n\nAUTOMATIC RESUME CONTEXT: This is a retry of the same "
                f"outer iteration. Proposal run_id={run_id} is already approved. "
                "Do not restart literature review, author another method, or submit "
                "another proposal. Trusted orchestration has already created and "
                "registered the native AutoData workspace"
                + (f" workspace_id={workspace_id}" if workspace_id else "")
                + ". Resume its visible host action or "
                "execution and finish its verified production handoff before training."
            )
        return task

    async def _wait_for_training_result(self) -> None:
        """Keep Kimi out of shell polling while the asynchronous job/evaluator runs."""
        if self.completion_tool != "share_finding":
            return
        run_id = self._approved_run_id()
        if run_id is None:
            return
        job_id = self._current_training_job_id(run_id)
        if job_id is None:
            return
        score_path = self._score_path_for_run(run_id)
        if score_path is None or score_path.is_file():
            return
        timeout_seconds = int(os.environ.get("AAR_KIMI_SCORE_WAIT_SECONDS", "10800"))
        deadline = time.monotonic() + timeout_seconds
        next_update = time.monotonic()
        next_scheduler_check = time.monotonic()
        while time.monotonic() < deadline:
            if score_path.is_file():
                print(f"[Kimi] score ready for approved run {run_id}")
                return
            failure = self._current_training_failure()
            if failure is not None:
                raise RuntimeError(
                    "Kimi training failed closed: "
                    + json.dumps(failure, sort_keys=True)[:2000]
                )
            if time.monotonic() >= next_scheduler_check:
                failure = self._reconcile_terminal_training_job(run_id, job_id)
                if failure is not None:
                    raise RuntimeError(
                        "Kimi training failed closed: "
                        + json.dumps(failure, sort_keys=True)[:2000]
                    )
                next_scheduler_check = time.monotonic() + 30
            if time.monotonic() >= next_update:
                print(f"[Kimi] waiting for score from training job {job_id}")
                next_update = time.monotonic() + 60
            await asyncio.sleep(10)
        raise RuntimeError(
            f"timed out waiting for score or failure marker for approved run {run_id}"
        )

    @staticmethod
    def _slurm_job_result(job_id: str) -> Optional[tuple[str, int | None]]:
        """Return Slurm's normalized state and process-style exit code, if known."""
        try:
            completed = subprocess.run(
                [
                    "sacct",
                    "-j",
                    job_id,
                    "-X",
                    "-n",
                    "-P",
                    "-o",
                    "State,ExitCode",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        for line in completed.stdout.splitlines():
            fields = line.strip().split("|")
            if not fields or not fields[0].strip():
                continue
            state = fields[0].split()[0].rstrip("+").upper()
            exit_code = None
            if len(fields) > 1:
                match = re.fullmatch(r"([0-9]+):([0-9]+)", fields[1].strip())
                if match:
                    status, signal = (int(value) for value in match.groups())
                    exit_code = status if status else (128 + signal if signal else 0)
            return state, exit_code
        return None

    @classmethod
    def _reconcile_terminal_training_job(
        cls, run_id: str, job_id: str
    ) -> Optional[dict[str, Any]]:
        """Publish the missing handoff when Slurm kills a job before its EXIT trap."""
        result = cls._slurm_job_result(job_id)
        if result is None:
            return None
        state, exit_code = result
        terminal_failures = {
            "BOOT_FAIL",
            "CANCELLED",
            "DEADLINE",
            "FAILED",
            "NODE_FAIL",
            "OUT_OF_MEMORY",
            "PREEMPTED",
            "REVOKED",
            "SPECIAL_EXIT",
            "TIMEOUT",
        }
        if state not in terminal_failures:
            return None
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        if not scores_dir:
            return None
        from aar.eval_pod.failure import publish_failure

        log_path = None
        team_dir = os.environ.get("TEAM_DIR", "").strip()
        if team_dir:
            log_path = Path(team_dir) / "logs" / f"train-{job_id}.out"
        try:
            failure_path = publish_failure(
                scores_dir,
                run_id,
                f"Slurm training job {job_id} ended in {state} before model scoring",
                stage="training",
                error_code=f"training_slurm_{state.lower()}",
                retryable=state
                in {"BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED"},
                exit_code=exit_code,
                log_path=log_path,
            )
        except FileExistsError:
            return None
        try:
            payload = json.loads(failure_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _current_training_failure(cls) -> Optional[dict[str, Any]]:
        run_id = cls._approved_run_id()
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        if run_id is None or not scores_dir:
            return None
        path = Path(scores_dir) / f"{run_id}.failed.json"
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else {"error": str(payload)}

    @classmethod
    def _previous_failure_feedback(cls) -> Optional[dict[str, Any]]:
        """Return the latest unscored failure for the next Kimi session."""

        run_id = cls._approved_run_id()
        if run_id is None:
            return None
        score_path = cls._score_path_for_run(run_id)
        if score_path is not None and score_path.is_file():
            return None
        failure = cls._current_training_failure()
        if failure is None:
            return None
        allowed_fields = (
            "schema_version",
            "status",
            "run_id",
            "stage",
            "error_code",
            "exception_type",
            "error",
            "reason",
            "retryable",
            "exit_code",
            "log_path",
            "eval_job_id",
        )
        return {key: failure[key] for key in allowed_fields if key in failure}

    @classmethod
    def _with_previous_failure_feedback(cls, task: str) -> str:
        feedback = cls._previous_failure_feedback()
        if feedback is None:
            return task
        return (
            task
            + "\n\nAUTOMATIC HELD-OUT-SAFE FAILURE FEEDBACK FROM YOUR PREVIOUS "
            "CANDIDATE:\n"
            + json.dumps(feedback, sort_keys=True)
            + "\nBefore proposing another method, diagnose and fix this exact failure. "
            "Read log_path when present, record the cause in your chain memory, "
            "and do not resubmit the unchanged method. This feedback contains no "
            "held-out examples or partial held-out scores."
        )

    @staticmethod
    def _score_path_for_run(run_id: str) -> Optional[Path]:
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        if not scores_dir:
            return None
        return Path(scores_dir) / f"{run_id}.json"

    @staticmethod
    def _current_score_path() -> Optional[Path]:
        run_id_file = Path("/tmp/run_id_current")
        scores_dir = os.environ.get("SCORES_DIR", "").strip()
        if not run_id_file.is_file() or not scores_dir:
            return None
        try:
            run_id = run_id_file.read_text().strip()
        except OSError:
            return None
        if not run_id or not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
            return None
        score_path = Path(scores_dir) / f"{run_id}.json"
        if score_path.is_file():
            return score_path
        failed_path = Path(scores_dir) / f"{run_id}.failed.json"
        return failed_path if failed_path.is_file() else score_path

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
                if child.name == "config.toml" and self.auto_approve:
                    config_text = child.read_text()
                    permission = 'defaultPermissionMode = "auto"'
                    if re.search(
                        r"(?m)^\s*defaultPermissionMode\s*=.*$", config_text
                    ):
                        config_text = re.sub(
                            r"(?m)^\s*defaultPermissionMode\s*=.*$",
                            permission,
                            config_text,
                        )
                    else:
                        config_text = f"{permission}\n{config_text}"
                    (overlay_home / child.name).write_text(config_text)
                    continue
                (overlay_home / child.name).symlink_to(
                    child, target_is_directory=child.is_dir()
                )
        if self.auto_approve and not (overlay_home / "config.toml").exists():
            (overlay_home / "config.toml").write_text(
                'defaultPermissionMode = "auto"\n'
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
    def _request_policy_proxy(
        self, env: dict[str, str]
    ) -> Iterator[_ToolChoiceController]:
        """Apply opt-in request fields unsupported by Kimi Code's provider config."""
        disable_thinking = env.get("AAR_KIMI_DISABLE_THINKING", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        controller = _ToolChoiceController()
        if not disable_thinking and not self.force_checkpoint_tools:
            yield controller
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
            disable_thinking=disable_thinking,
            tool_choice_controller=controller,
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
            yield controller
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
