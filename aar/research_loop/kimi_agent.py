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
from typing import Any, Callable, Iterator, NoReturn, Optional
from urllib.parse import urlsplit

import requests

from aar.failure_feedback import (
    FailureFeedbackError,
    build_failure_feedback,
    safe_failure_feedback_view,
)


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
    failure: Optional[dict[str, Any]] = None


class OrchestrationIncident(RuntimeError):
    """Shared infrastructure failure that research sessions cannot repair."""

    def __init__(
        self,
        message: str,
        *,
        failure: dict[str, Any] | None = None,
    ) -> None:
        self.failure = failure
        super().__init__(message)


class AutoDataActionResultValidationError(RuntimeError):
    """A researcher-authored result can be corrected before native completion."""


def _retain_process_failure(
    *,
    error: BaseException,
    error_code: str,
    stage: str,
    public_summary: str,
    retryable: bool = False,
) -> FailureFeedbackError:
    feedback = build_failure_feedback(
        error,
        error_code=error_code,
        stage=stage,
        retryable=retryable,
        public_summary=public_summary,
    )
    return FailureFeedbackError(feedback)


PROTECTED_SUBMISSION_FILES = (
    "scripts/submit_train_job.sh",
    "scripts/slurm_train_submit.sh",
    "scripts/aar_runtime_env.sh",
    "scripts/validate_method_contract.py",
)


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
        self._argument_schema: dict[str, dict[str, Any]] = {}

    def arm(
        self,
        tool_name: Optional[str],
        *,
        argument_schema: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        with self._lock:
            self._pending = tool_name
            self._argument_schema = argument_schema or {}

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
            if self._argument_schema:
                selected = next(
                    item
                    for item in tools
                    if isinstance(item, dict)
                    and isinstance(item.get("function"), dict)
                    and item["function"].get("name") == matches[0]
                )
                function = selected["function"]
                parameters = function.setdefault(
                    "parameters", {"type": "object", "properties": {}}
                )
                if not isinstance(parameters, dict):
                    raise ValueError(
                        f"required Kimi checkpoint tool {requested!r} has no "
                        "object parameter schema"
                    )
                properties = parameters.setdefault("properties", {})
                if not isinstance(properties, dict):
                    raise ValueError(
                        f"required Kimi checkpoint tool {requested!r} has invalid "
                        "parameter properties"
                    )
                required = parameters.setdefault("required", [])
                if not isinstance(required, list) or not all(
                    isinstance(name, str) for name in required
                ):
                    raise ValueError(
                        f"required Kimi checkpoint tool {requested!r} has invalid "
                        "required parameters"
                    )
                for name, schema in self._argument_schema.items():
                    existing = properties.get(name)
                    if existing is not None and not isinstance(existing, dict):
                        raise ValueError(
                            f"required Kimi checkpoint argument {name!r} has an "
                            "invalid schema"
                        )
                    properties[name] = {**(existing or {}), **schema}
                    if name not in required:
                        required.append(name)
            self._pending = None
            self._argument_schema = {}
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
        force_completion_tool_first_turn: bool = False,
        max_checkpoint_retries: Optional[int] = None,
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
        if force_completion_tool_first_turn and not completion_tool:
            raise ValueError(
                "force_completion_tool_first_turn requires completion_tool"
            )
        self.force_completion_tool_first_turn = force_completion_tool_first_turn
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
        if max_checkpoint_retries is None:
            raw_checkpoint_retries = os.getenv(
                "AAR_KIMI_MAX_CHECKPOINT_RETRIES", "2"
            )
            try:
                max_checkpoint_retries = int(raw_checkpoint_retries)
            except ValueError as error:
                raise ValueError(
                    "AAR_KIMI_MAX_CHECKPOINT_RETRIES must be an integer"
                ) from error
        if max_checkpoint_retries < 0:
            raise ValueError(
                "Kimi max_checkpoint_retries must be zero or greater"
            )
        self.max_checkpoint_retries = max_checkpoint_retries
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
        except OrchestrationIncident:
            raise
        except Exception as error:
            if isinstance(error, FailureFeedbackError):
                feedback = dict(error.feedback)
            else:
                feedback = _retain_process_failure(
                    error=error,
                    error_code="kimi_session_failed",
                    stage="research_session",
                    public_summary="Kimi research session failed",
                ).feedback
            return KimiAgentResult(
                success=False,
                output={},
                duration=time.time() - start_time,
                iteration_count=0,
                error=str(feedback["summary"]),
                failure=feedback,
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
        checkpoint_retry_count = 0
        autodata_wait_deadline: float | None = None
        autodata_idle_deadline: float | None = None

        with tempfile.TemporaryDirectory(prefix="aar-kimi-") as temp_dir:
            overlay_home = Path(temp_dir)
            env = self._build_environment(overlay_home)
            agent_file = self._write_agent_profile(overlay_home)
            with self._request_policy_proxy(env) as tool_choice_controller:
                while True:
                    host_resume = bool(continuation_count) or (
                        self._resume_approved_proposal_enabled()
                    )
                    if host_resume and self._owns_approved_run(output):
                        approved_run_id = self._approved_run_id()
                        if (
                            approved_run_id is None
                            and self._resume_approved_proposal_enabled()
                        ):
                            self._raise_orchestration_incident(
                                "approved-proposal recovery has no fully bound trusted "
                                "run_id; refusing to start a new model workflow"
                            )
                        if approved_run_id is not None:
                            if self._autodata_enabled():
                                if self._autodata_handoff_ready(approved_run_id):
                                    if self._autodata_stop_after_production():
                                        self._complete_autodata_production_canary(
                                            approved_run_id
                                        )
                                        break
                                    self._ensure_approved_training_submission()
                                    if self._autodata_stop_after_training_smoke():
                                        await self._wait_for_training_smoke_result()
                                        self._complete_autodata_training_smoke_canary(
                                            approved_run_id
                                        )
                                        break
                                    await self._wait_for_training_result()
                            else:
                                # Native decoupled recovery is host-owned too. Do
                                # not spend a model turn asking Kimi to rediscover
                                # or shell-submit an already-approved run.
                                self._ensure_approved_training_submission()
                                await self._wait_for_training_result()
                    if host_resume and self._autodata_wait_required(output):
                        approved_run_id = self._approved_run_id()
                        assert approved_run_id is not None
                        workspace_id = self._autodata_workspace_id(approved_run_id)
                        if workspace_id is None:
                            raise RuntimeError(
                                "approved AutoData proposal has no registered workspace"
                            )
                        status_subject = self._autodata_status_subject(workspace_id)
                        action = self._autodata_pending_action_record(
                            workspace_id, status_subject
                        )
                        if action is None:
                            supervisor_status = (
                                self._require_fresh_autodata_supervisor_status()
                            )
                            if (
                                supervisor_status is not None
                                and supervisor_status.get("state") == "idle"
                            ):
                                if autodata_idle_deadline is None:
                                    idle_grace = float(
                                        os.getenv(
                                            "AAR_AUTODATA_HOST_IDLE_GRACE_SECONDS",
                                            "90",
                                        )
                                    )
                                    if idle_grace <= 0:
                                        raise RuntimeError(
                                            "AAR_AUTODATA_HOST_IDLE_GRACE_SECONDS "
                                            "must be positive"
                                        )
                                    autodata_idle_deadline = (
                                        time.monotonic() + idle_grace
                                    )
                                elif time.monotonic() >= autodata_idle_deadline:
                                    raise _retain_process_failure(
                                        error=RuntimeError(
                                            "AutoData supervisor remained idle without "
                                            "a scoped action or verified handoff"
                                        ),
                                        error_code="autodata_supervisor_idle_stall",
                                        stage="autodata_lifecycle",
                                        public_summary=(
                                            "AutoData lifecycle stalled without work"
                                        ),
                                    )
                            else:
                                autodata_idle_deadline = None
                            if autodata_wait_deadline is None:
                                timeout = float(
                                    os.getenv(
                                        "AAR_AUTODATA_HOST_WAIT_SECONDS", "10800"
                                    )
                                )
                                if timeout <= 0:
                                    raise RuntimeError(
                                        "AAR_AUTODATA_HOST_WAIT_SECONDS must be positive"
                                    )
                                autodata_wait_deadline = time.monotonic() + timeout
                            if time.monotonic() >= autodata_wait_deadline:
                                raise RuntimeError(
                                    "timed out waiting for the AutoData lifecycle "
                                    "supervisor to expose a scoped host action or handoff"
                                )
                            snapshot = self._autodata_native_status(status_subject)
                            status = self._autodata_subject_status(
                                status_subject, snapshot
                            )
                            if status in {"failed", "cancelled", "error"}:
                                nested = snapshot.get("failure")
                                safe_nested = safe_failure_feedback_view(nested)
                                if safe_nested is not None:
                                    raise FailureFeedbackError(safe_nested)
                                raise FailureFeedbackError(
                                    build_failure_feedback(
                                        RuntimeError(status),
                                        error_code="autodata_lifecycle_failed",
                                        stage="autodata_lifecycle",
                                        public_summary=(
                                            "AutoData lifecycle terminated before handoff"
                                        ),
                                    )
                                )
                            print(
                                "[Kimi] host FSM waiting without a model turn: "
                                f"subject={status_subject} status={status or 'unknown'}"
                            )
                            await asyncio.sleep(
                                min(
                                    10.0,
                                    max(0.0, autodata_wait_deadline - time.monotonic()),
                                )
                            )
                            continue
                        autodata_wait_deadline = None
                        autodata_idle_deadline = None
                        if action["status"] == "in_progress":
                            if action["kind"] not in {
                                "approve_grounding",
                                "approve_baseline",
                                "approve_resources",
                            }:
                                self._autodata_require_action_lease(
                                    str(action["id"])
                                )
                                result_path = self._autodata_action_result_path(
                                    str(action["id"])
                                )
                                if result_path.is_file() and not (
                                    self._autodata_pipeline_feedback_requires_edit(
                                        action
                                    )
                                ):
                                    try:
                                        self._autodata_complete_action(
                                            str(action["id"]), result_path
                                        )
                                    except AutoDataActionResultValidationError as error:
                                        print(
                                            "[Kimi] host FSM rejected correctable action "
                                            f"result: {error}"
                                        )
                                    else:
                                        print(
                                            "[Kimi] host FSM completed durable action "
                                            f"result without a model turn: {action['id']}"
                                        )
                                        continue
                    command = [executable]
                    if self.model:
                        command.extend(["--model", self.model])
                    if continuation_count:
                        command.append("--continue")
                        current_prompt = self._continuation_prompt(output)
                        required_tool = self._continuation_tool(
                            output, prompt=current_prompt
                        )
                    else:
                        if agent_file is not None:
                            command.extend(["--agent-file", str(agent_file)])
                        current_prompt = prompt
                        required_tool = (
                            self.completion_tool
                            if self.force_completion_tool_first_turn
                            else None
                        )
                    checkpoint_tool = (
                        required_tool
                        if self.force_checkpoint_tools
                        or (
                            continuation_count == 0
                            and self.force_completion_tool_first_turn
                        )
                        else None
                    )
                    tool_choice_controller.arm(
                        checkpoint_tool,
                        argument_schema=self._checkpoint_argument_schema(
                            checkpoint_tool
                        ),
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
                        retryable = bool(
                            detail
                            and any(
                                token in detail.lower()
                                for token in ("529", "overloaded", "temporarily unavailable")
                            )
                        )
                        raise _retain_process_failure(
                            error=RuntimeError(f"Kimi CLI exit {return_code}"),
                            error_code=(
                                "kimi_model_overloaded"
                                if retryable
                                else "kimi_cli_failed"
                            ),
                            stage="research_session",
                            public_summary=(
                                "Kimi model service is overloaded"
                                if retryable
                                else f"Kimi Code exited with status {return_code}"
                            ),
                            retryable=retryable,
                        )
                    if required_tool is not None and new_tool_uses == 0:
                        if checkpoint_retry_count >= self.max_checkpoint_retries:
                            raise FailureFeedbackError(
                                build_failure_feedback(
                                    RuntimeError("required checkpoint missing"),
                                    error_code="required_checkpoint_missing",
                                    stage="research_session",
                                    public_summary=(
                                        "Kimi repeatedly stopped without calling required "
                                        f"checkpoint tool {required_tool} after "
                                        f"{self.max_checkpoint_retries} retries"
                                    ),
                                )
                            )
                        checkpoint_retry_count += 1
                        print(
                            "[Kimi] stalled required checkpoint; retrying "
                            f"{required_tool} ({checkpoint_retry_count}/"
                            f"{self.max_checkpoint_retries}) without consuming the "
                            "productive continuation budget"
                        )
                        continue
                    checkpoint_retry_count = 0
                    # Proposal markers persist across AutonomousAgentLoop sessions.
                    # Only the session that actually submitted the proposal may act
                    # on that marker; otherwise one failed run poisons every later
                    # session and burns the iteration budget without allowing a fix.
                    owns_approved_run = (
                        self._submitted_proposal_in_output(output)
                        and self._proposal_marker_changed_this_session()
                    ) or self._resume_approved_proposal_enabled()
                    bounded_canary_complete = False
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
                                bounded_canary_complete = True
                            elif self._autodata_stop_after_training_smoke():
                                self._ensure_approved_training_submission()
                                await self._wait_for_training_smoke_result()
                                self._complete_autodata_training_smoke_canary(
                                    approved_run_id
                                )
                                bounded_canary_complete = True
                            else:
                                self._ensure_approved_training_submission()
                                await self._wait_for_training_result()
                                training_failure = self._current_training_failure()
                                score_path = self._score_path_for_run(approved_run_id)
                                if training_failure is not None and not (
                                    score_path is not None and score_path.is_file()
                                ):
                                    raise FailureFeedbackError(training_failure)
                    if bounded_canary_complete:
                        break
                    if not self.completion_tool or self._completion_tool_used(output):
                        break
                    if continuation_count >= self.max_continuations:
                        raise FailureFeedbackError(
                            build_failure_feedback(
                                RuntimeError("required completion missing"),
                                error_code="required_completion_missing",
                                stage="research_session",
                                public_summary=(
                                    "Kimi stopped before calling the required completion "
                                    f"tool {self.completion_tool} after "
                                    f"{self.max_continuations} continuations"
                                ),
                            )
                        )
                    continuation_count += 1
                    print(
                        f"[Kimi] resuming incomplete session "
                        f"({continuation_count}/{self.max_continuations})"
                    )

        if not output["text_outputs"] and not output["tool_uses"]:
            raise FailureFeedbackError(
                build_failure_feedback(
                    RuntimeError("empty Kimi response"),
                    error_code="kimi_empty_response",
                    stage="research_session",
                    public_summary="Kimi Code ended without an assistant response",
                )
            )

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
                raise FailureFeedbackError(
                    build_failure_feedback(
                        error,
                        error_code="kimi_turn_timeout",
                        stage="research_session",
                        retryable=True,
                        public_summary=(
                            "Kimi Code turn exceeded "
                            f"{self.turn_timeout_seconds:g} seconds and its process "
                            "group was terminated"
                        ),
                    )
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
        return self._finding_persisted_for_run(run_id)

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
        incomplete_finding_attempt = any(
            name == "share_finding"
            and (
                inputs[index].get("run_id") != approved_run_id
                or not isinstance(inputs[index].get("results_writeup"), str)
                or len(inputs[index]["results_writeup"].strip()) < 80
            )
            for index, name in enumerate(names)
        )

        if approved_run_id is not None and incomplete_finding_attempt:
            return (
                "The previous share_finding attempt did not persist because its "
                "structured arguments were incomplete or incorrectly bound. Call the "
                "native structured MCP tool share_finding exactly once now. In that "
                "SAME structured call, pass run_id="
                f"{json.dumps(approved_run_id)} exactly and pass results_writeup as a "
                "single string of at least 80 characters explaining which public "
                "benchmarks moved or did not, capability behavior, mechanism, and "
                "limitations. Do not split these fields across calls, use another run "
                "ID, emit prose, or call another tool."
            )

        if (
            approved_run_id is not None
            and self._autodata_enabled()
            and not self._autodata_handoff_ready(approved_run_id)
        ):
            workspace_id = self._autodata_workspace_id(approved_run_id)
            if workspace_id is not None:
                status_subject = self._autodata_status_subject(workspace_id)
                action = self._autodata_pending_action_record(
                    workspace_id, status_subject
                )
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
                    result_path = self._autodata_action_result_path(action["id"])
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
                        validation_feedback = ""
                        feedback_path = self._autodata_action_result_feedback_path(
                            str(action["id"])
                        )
                        if feedback_path.is_file() and not feedback_path.is_symlink():
                            validation_feedback = (
                                " The previous result was rejected before native "
                                "completion: "
                                + feedback_path.read_text(encoding="utf-8").strip()[:1000]
                                + ". Rewrite the complete result JSON now."
                            )
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
                            f"{result_path} satisfying the requested outputs."
                            f"{validation_feedback} Use only "
                            "the action instructions and allowed paths; do not use Bash. "
                            f"Action specification: {action_spec}. "
                            f"Current allowed-file content: {editable_context}"
                        )
                    self._autodata_complete_action(action["id"], result_path)
                status_snapshot = self._autodata_native_status(status_subject)
                raise RuntimeError(
                    "host FSM reached a model continuation with no scoped AutoData "
                    "action; deterministic waits must be handled without Kimi: "
                    + json.dumps(status_snapshot, sort_keys=True)[:4000]
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
                if self._autodata_enabled():
                    raise RuntimeError(
                        "trusted host must submit approved AutoData training before "
                        "a researcher continuation; refusing model-controlled submission"
                    )
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
            if approved is True:
                self._raise_orchestration_incident(
                    "approved decoupled proposal is missing its trusted run_id; "
                    "refusing to spend model continuations or invent an execution ID"
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

    def _continuation_tool(
        self, output: dict[str, Any], *, prompt: str | None = None
    ) -> Optional[str]:
        """Return the one tool required by the current fail-closed checkpoint."""
        if self.completion_tool != "share_finding":
            return self.completion_tool
        if prompt is None:
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

    def _checkpoint_argument_schema(
        self, required_tool: Optional[str]
    ) -> dict[str, dict[str, Any]]:
        """Bind forced result publication to one complete, approved tool call."""
        if required_tool != "share_finding":
            return {}
        run_id = self._approved_run_id()
        if run_id is None:
            return {}
        return {
            "run_id": {"type": "string", "const": run_id},
            "results_writeup": {"type": "string", "minLength": 80},
        }

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
            raise _retain_process_failure(
                error=RuntimeError("trusted native AutoData state is unavailable"),
                error_code="autodata_action_state_unavailable",
                stage="autodata_action",
                public_summary="trusted AutoData action state is unavailable",
            )
        try:
            with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
                row = connection.execute(
                    "SELECT kind,status,specJson FROM actions WHERE id=?",
                    (action_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise _retain_process_failure(
                error=error,
                error_code="autodata_action_state_query_failed",
                stage="autodata_action",
                public_summary="trusted AutoData action state could not be queried",
            ) from error
        if row is None:
            return None
        try:
            spec = json.loads(str(row[2]))
        except json.JSONDecodeError as error:
            raise _retain_process_failure(
                error=error,
                error_code="autodata_action_record_invalid",
                stage="autodata_action",
                public_summary="trusted AutoData action record is invalid",
            ) from error
        if not isinstance(spec, dict):
            raise _retain_process_failure(
                error=TypeError("native action spec is not an object"),
                error_code="autodata_action_record_invalid",
                stage="autodata_action",
                public_summary="trusted AutoData action record is invalid",
            )
        return {
            "id": action_id,
            "kind": str(row[0]),
            "status": str(row[1]),
            "spec": spec,
        }

    @staticmethod
    def _autodata_pending_action_record(
        *allowed_scope_ids: str,
    ) -> dict[str, Any] | None:
        """Return the sole live action scoped to this run, never a global action."""
        state_raw = os.environ.get("AAR_AUTODATA_STATE", "").strip()
        if not state_raw:
            return None
        state = Path(state_raw)
        if state.is_symlink() or not state.is_file():
            raise _retain_process_failure(
                error=RuntimeError("trusted native AutoData state is unavailable"),
                error_code="autodata_action_state_unavailable",
                stage="autodata_action",
                public_summary="trusted AutoData action state is unavailable",
            )
        try:
            with sqlite3.connect(f"file:{state}?mode=ro", uri=True) as connection:
                rows = connection.execute(
                    "SELECT id FROM actions WHERE status IN ('pending','in_progress') "
                    "ORDER BY createdAt,id"
                ).fetchall()
        except sqlite3.Error as error:
            raise _retain_process_failure(
                error=error,
                error_code="autodata_action_state_query_failed",
                stage="autodata_action",
                public_summary="trusted AutoData action state could not be queried",
            ) from error
        allowed = {value for value in allowed_scope_ids if value}
        matches: list[dict[str, Any]] = []
        for row in rows:
            action = KimiAgent._autodata_action_record(str(row[0]))
            if action is None:
                continue
            scope = action["spec"].get("scope")
            if (
                isinstance(scope, dict)
                and scope.get("kind") in {"workspace", "execution"}
                and scope.get("id") in allowed
            ):
                matches.append(action)
        if len(matches) > 1:
            raise RuntimeError(
                "ambiguous AutoData host actions for the current run: "
                + ", ".join(str(action["id"]) for action in matches)
            )
        return matches[0] if matches else None

    @staticmethod
    def _require_fresh_autodata_supervisor_status() -> dict[str, Any] | None:
        """Reject a dead/corrupt supervised lifecycle instead of waiting hours."""
        if os.environ.get("AAR_AUTODATA_LIFECYCLE_SUPERVISED", "0") != "1":
            return None
        raw_path = os.environ.get("AAR_AUTODATA_SUPERVISOR_STATUS", "").strip()
        if not raw_path:
            raise _retain_process_failure(
                error=RuntimeError("AutoData supervisor status path is not configured"),
                error_code="autodata_supervisor_status_missing",
                stage="autodata_lifecycle",
                public_summary="AutoData lifecycle supervisor status is unavailable",
            )
        path = Path(raw_path)
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("supervisor status is not a regular file")
            value = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(value, dict)
                or value.get("schema") != "aar.autodata.lifecycle-supervisor/v1"
            ):
                raise ValueError("supervisor status has the wrong schema")
            updated_raw = value.get("updated_at")
            if not isinstance(updated_raw, str):
                raise ValueError("supervisor status has no update timestamp")
            updated = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                raise ValueError("supervisor update timestamp has no timezone")
            age = time.time() - updated.timestamp()
            maximum_age = float(
                os.environ.get("AAR_AUTODATA_SUPERVISOR_HEARTBEAT_SLA_SECONDS", "180")
            )
            if maximum_age <= 0:
                raise ValueError("supervisor heartbeat SLA must be positive")
            if age < -60 or age > maximum_age:
                raise TimeoutError("supervisor heartbeat is stale")
        except (OSError, ValueError, json.JSONDecodeError, TimeoutError) as error:
            raise _retain_process_failure(
                error=error,
                error_code="autodata_supervisor_heartbeat_invalid",
                stage="autodata_lifecycle",
                public_summary="AutoData lifecycle supervisor heartbeat is invalid",
            ) from error
        state = value.get("state")
        if state == "failed":
            feedback = safe_failure_feedback_view(value.get("failure"))
            if feedback is not None:
                raise FailureFeedbackError(feedback)
            raise _retain_process_failure(
                error=RuntimeError("AutoData lifecycle supervisor failed"),
                error_code="autodata_supervisor_failed",
                stage="autodata_lifecycle",
                public_summary="AutoData lifecycle supervisor failed",
            )
        if state not in {
            "starting",
            "running",
            "stepping",
            "idle",
            "reconciling",
            "reconcile-retrying",
        }:
            raise _retain_process_failure(
                error=RuntimeError(
                    f"AutoData lifecycle supervisor is not runnable: {state!r}"
                ),
                error_code="autodata_supervisor_state_invalid",
                stage="autodata_lifecycle",
                public_summary="AutoData lifecycle supervisor is not runnable",
            )
        return value

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
            raise _retain_process_failure(
                error=RuntimeError(
                    f"trusted AutoData action bridge exit {completed.returncode}"
                ),
                error_code="autodata_action_bridge_failed",
                stage="autodata_action",
                public_summary=(
                    "trusted AutoData action bridge command failed "
                    f"(exit {completed.returncode})"
                ),
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise _retain_process_failure(
                error=error,
                error_code="autodata_action_bridge_invalid_json",
                stage="autodata_action",
                public_summary=(
                    "trusted AutoData action bridge returned invalid JSON"
                ),
            ) from error
        if not isinstance(payload, dict):
            raise RuntimeError("trusted AutoData action bridge returned a non-object")
        return payload

    @staticmethod
    def _autodata_action_lease_path(action_id: str) -> Path:
        team_raw = os.environ.get("TEAM_DIR", "").strip()
        if not team_raw:
            raise RuntimeError("TEAM_DIR is required for AutoData action leases")
        root = Path(team_raw) / "autodata" / "action-leases"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root / f"{action_id}.token"

    @staticmethod
    def _autodata_action_result_path(action_id: str) -> Path:
        team_raw = os.environ.get("TEAM_DIR", "").strip()
        if not team_raw:
            raise RuntimeError("TEAM_DIR is required for AutoData action results")
        root = Path(team_raw) / "autodata" / "action-results"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root / f"{action_id}.json"

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
    def _autodata_action_result_feedback_path(action_id: str) -> Path:
        team_raw = os.environ.get("TEAM_DIR", "").strip()
        if not team_raw:
            raise RuntimeError("TEAM_DIR is required for AutoData action results")
        root = Path(team_raw) / "autodata" / "action-results"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root / f"{action_id}.validation.txt"

    @staticmethod
    def _write_private_text(path: Path, value: str) -> None:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent, text=True
        )
        temporary = Path(raw_temporary)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _autodata_begin_action(cls, action: dict[str, Any]) -> None:
        action_id = action.get("id")
        if not isinstance(action_id, str):
            raise RuntimeError("trusted AutoData action has no identifier")
        lease_path = cls._autodata_action_lease_path(action_id)
        if action.get("status") == "in_progress":
            cls._autodata_require_action_lease(action_id)
            return
        if lease_path.exists():
            raise RuntimeError(
                "pending AutoData action unexpectedly has a durable lease token"
            )
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
    def _autodata_require_action_lease(cls, action_id: str) -> str:
        lease_path = cls._autodata_action_lease_path(action_id)
        try:
            token = lease_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise RuntimeError(
                "native AutoData action is in_progress but its durable lease token "
                "is missing; refusing to invoke the researcher model"
            ) from error
        if len(token) < 20:
            raise RuntimeError("trusted AutoData action lease is invalid")
        return token

    @classmethod
    def _autodata_normalize_action_result(
        cls,
        action: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the exact flat result shape consumed by native AutoData."""
        action_id = action.get("id")
        spec = action.get("spec")
        if not isinstance(action_id, str) or not isinstance(spec, dict):
            raise AutoDataActionResultValidationError(
                "native AutoData action metadata is incomplete"
            )
        declared = spec.get("outputs")
        if (
            not isinstance(declared, list)
            or not declared
            or any(not isinstance(name, str) or not name for name in declared)
            or len(set(declared)) != len(declared)
        ):
            raise AutoDataActionResultValidationError(
                "native AutoData action has invalid declared outputs"
            )

        if "outputs" in result:
            wrapper_keys = {"schema", "status", "action_id", "outputs"}
            if set(result) - wrapper_keys:
                raise AutoDataActionResultValidationError(
                    "action result mixes envelope and top-level output fields"
                )
            if result.get("schema") != "autodata.action-result/v1":
                raise AutoDataActionResultValidationError(
                    "action result envelope has the wrong schema"
                )
            if result.get("status") != "completed":
                raise AutoDataActionResultValidationError(
                    "action result envelope status must be completed"
                )
            wrapped_action_id = result.get("action_id")
            if wrapped_action_id is not None and wrapped_action_id != action_id:
                raise AutoDataActionResultValidationError(
                    "action result envelope names the wrong action"
                )
            outputs = result.get("outputs")
            if not isinstance(outputs, dict):
                raise AutoDataActionResultValidationError(
                    "action result envelope outputs must be one JSON object"
                )
            normalized = dict(outputs)
        else:
            normalized = dict(result)

        missing = [name for name in declared if name not in normalized]
        unexpected = sorted(set(normalized) - set(declared))
        if missing:
            raise AutoDataActionResultValidationError(
                "action result is missing declared output(s): " + ", ".join(missing)
            )
        if unexpected:
            raise AutoDataActionResultValidationError(
                "action result has undeclared output(s): " + ", ".join(unexpected)
            )
        for name in declared:
            value = normalized[name]
            if value is None:
                raise AutoDataActionResultValidationError(
                    f"action result output {name!r} must not be null"
                )
            if name in {"proposal", "summary"} and (
                not isinstance(value, str) or not value.strip()
            ):
                raise AutoDataActionResultValidationError(
                    f"action result output {name!r} must be a non-empty string"
                )
            if name == "decisions" and not isinstance(value, list):
                raise AutoDataActionResultValidationError(
                    "action result output 'decisions' must be a list"
                )
            if name == "dashboard_summary" and not isinstance(value, dict):
                raise AutoDataActionResultValidationError(
                    "action result output 'dashboard_summary' must be an object"
                )
        return {name: normalized[name] for name in declared}

    @classmethod
    def _autodata_complete_action(cls, action_id: str, result_path: Path) -> None:
        action = cls._autodata_action_record(action_id)
        if action is None or action.get("status") != "in_progress":
            raise RuntimeError("native AutoData action is unavailable for completion")
        if result_path.is_symlink() or not result_path.is_file():
            raise RuntimeError("AutoData action result must be a regular file")
        try:
            result = json.loads(result_path.read_text())
        except json.JSONDecodeError as error:
            validation_error = AutoDataActionResultValidationError(
                "action result is not valid JSON"
            )
            cls._write_private_text(
                cls._autodata_action_result_feedback_path(action_id),
                str(validation_error),
            )
            result_path.unlink(missing_ok=True)
            raise validation_error from error
        except OSError as error:
            raise RuntimeError("AutoData action result could not be read") from error
        if not isinstance(result, dict):
            validation_error = AutoDataActionResultValidationError(
                "action result must be one JSON object"
            )
            cls._write_private_text(
                cls._autodata_action_result_feedback_path(action_id),
                str(validation_error),
            )
            result_path.unlink(missing_ok=True)
            raise validation_error
        lease_path = cls._autodata_action_lease_path(action_id)
        token = cls._autodata_require_action_lease(action_id)
        try:
            normalized = cls._autodata_normalize_action_result(action, result)
        except AutoDataActionResultValidationError as error:
            cls._write_private_text(
                cls._autodata_action_result_feedback_path(action_id), str(error)
            )
            result_path.unlink(missing_ok=True)
            raise
        cls._write_private_text(
            result_path,
            json.dumps(normalized, sort_keys=True, separators=(",", ":")),
        )
        if action is not None and action["kind"] == "author_grounding":
            cls._autodata_repair_incomplete_grounding(action)
        cls._autodata_cli(
            "action",
            "complete",
            action_id,
            f"--lease-token={token}",
            "--result",
            str(result_path),
        )
        lease_path.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)
        cls._autodata_action_result_feedback_path(action_id).unlink(missing_ok=True)

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
            raise _retain_process_failure(
                error=RuntimeError(
                    f"reviewed grounding repair exit {completed.returncode}"
                ),
                error_code="grounding_repair_failed",
                stage="autodata_grounding",
                public_summary="reviewed grounding repair failed",
            )
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
    def _autodata_subject_status(
        subject_id: str, snapshot: dict[str, Any]
    ) -> str:
        """Normalize and authenticate native workspace/execution status shapes."""
        if subject_id.startswith("ws_"):
            record = snapshot.get("workspace")
            identifier_key = "id"
        elif subject_id.startswith("exe_"):
            record = snapshot
            identifier_key = "execution_id"
        else:
            raise _retain_process_failure(
                error=RuntimeError(f"unsupported AutoData subject {subject_id}"),
                error_code="autodata_status_invalid",
                stage="autodata_lifecycle",
                public_summary="native AutoData status response is invalid",
            )
        status = record.get("status") if isinstance(record, dict) else None
        identifier = record.get(identifier_key) if isinstance(record, dict) else None
        if identifier != subject_id or status not in {
            "active",
            "frozen",
            "completed",
            "failed",
            "cancelled",
            "error",
        }:
            raise _retain_process_failure(
                error=RuntimeError(
                    f"native status for {subject_id} has an invalid identity or state"
                ),
                error_code="autodata_status_invalid",
                stage="autodata_lifecycle",
                public_summary="native AutoData status response is invalid",
            )
        return str(status)

    @staticmethod
    def _autodata_status_subject(workspace_id: str) -> str:
        """Return the current supervised subject in one durable run lineage."""
        control_raw = os.environ.get("AAR_AUTODATA_SUPERVISOR_CONTROL", "").strip()
        if not control_raw:
            if os.environ.get("AAR_AUTODATA_LIFECYCLE_SUPERVISED", "0") == "1":
                raise _retain_process_failure(
                    error=RuntimeError(
                        "supervised AutoData lifecycle control is not configured"
                    ),
                    error_code="autodata_lineage_control_unavailable",
                    stage="autodata_lifecycle",
                    public_summary=(
                        "trusted AutoData lifecycle control is unavailable"
                    ),
                )
            return workspace_id

        def fail(message: str) -> NoReturn:
            raise _retain_process_failure(
                error=RuntimeError(message),
                error_code="autodata_lineage_invalid",
                stage="autodata_lifecycle",
                public_summary="trusted AutoData lifecycle lineage is invalid",
            )

        control_path = Path(control_raw)
        try:
            if control_path.is_symlink() or not control_path.is_file():
                raise OSError("lifecycle control is not a regular file")
            control = json.loads(control_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise _retain_process_failure(
                error=error,
                error_code="autodata_lineage_control_unavailable",
                stage="autodata_lifecycle",
                public_summary="trusted AutoData lifecycle control is unavailable",
            ) from error
        if (
            not isinstance(control, dict)
            or set(control) != {"schema", "subjects"}
            or control.get("schema") != "aar.autodata.lifecycle-control/v1"
        ):
            fail("AutoData lifecycle control has an invalid schema")
        subjects = control.get("subjects")
        if not isinstance(subjects, list):
            fail("AutoData lifecycle control has no subjects array")
        entries: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in subjects:
            if not isinstance(entry, dict):
                fail("AutoData lifecycle control contains a non-object subject")
            kind = entry.get("kind")
            subject_id = entry.get("subject_id")
            status = entry.get("status")
            if (
                kind not in {"workspace", "execution"}
                or not isinstance(subject_id, str)
                or not subject_id
                or status not in {"registered", "completed"}
            ):
                fail("AutoData lifecycle control contains an invalid subject")
            key = (kind, subject_id)
            if key in entries:
                fail(f"AutoData lifecycle control duplicates {kind} {subject_id}")
            entries[key] = entry

        workspace = entries.get(("workspace", workspace_id))
        if workspace is None:
            fail(f"AutoData lifecycle control lost workspace {workspace_id}")
        canonical_id = workspace.get("canonical_execution_id")
        if canonical_id is None:
            if workspace["status"] != "registered":
                fail(
                    f"completed workspace {workspace_id} has no canonical execution"
                )
            return workspace_id
        if not isinstance(canonical_id, str) or not canonical_id:
            fail(f"workspace {workspace_id} has an invalid canonical execution")

        current_id = canonical_id
        seen: set[str] = set()
        while True:
            if current_id in seen:
                fail(f"AutoData execution lineage contains a cycle at {current_id}")
            seen.add(current_id)
            current = entries.get(("execution", current_id))
            if current is None:
                # The supervisor durably binds an execution before enrolling it.
                # During that short reconciliation window, the previous registered
                # subject remains the only safe status target.
                if current_id == canonical_id and workspace["status"] == "registered":
                    return workspace_id
                fail(
                    f"AutoData execution {current_id} is bound but not registered"
                )
            production_id = current.get("production_execution_id")
            if production_id is None:
                return current_id
            if not isinstance(production_id, str) or not production_id:
                fail(f"execution {current_id} has an invalid production binding")
            production = entries.get(("execution", production_id))
            if production is None:
                # Meta-to-production reconciliation writes the durable intent before
                # enrolling the child. Continue observing meta for this brief window.
                if current["status"] == "registered":
                    return current_id
                fail(
                    f"production execution {production_id} is bound but not registered"
                )
            if production.get("parent_meta_execution_id") != current_id:
                fail(
                    f"production execution {production_id} has the wrong meta parent"
                )
            current_id = production_id

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
        explicit_run_id = marker.get("run_id")
        if explicit_run_id is not None:
            if not isinstance(explicit_run_id, str) or not re.fullmatch(
                r"[A-Za-z0-9._-]+", explicit_run_id
            ) or not explicit_run_id.startswith(f"{idea_uid}-"):
                return None
            stamp_path = marker_path.parent / "runs" / f"{explicit_run_id}.json"
            try:
                stamp = json.loads(stamp_path.read_text())
            except (OSError, json.JSONDecodeError):
                return None
            if (
                stamp.get("run_id") != explicit_run_id
                or stamp.get("idea_name") != idea_name
                or stamp.get("code_hash") != code_hash
                or stamp.get("paper") != marker.get("paper")
            ):
                return None
            return explicit_run_id

        # Legacy markers written before approval-time run IDs are supported only
        # by matching their immutable stamps. New decoupled approvals and repaired
        # recoveries always take the explicit, fully verified branch above.
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
        active_incident = self.active_orchestration_incident()
        if active_incident is not None:
            failure = safe_failure_feedback_view(
                active_incident.get("failure"),
                public_summary="team is paused by a shared orchestration incident",
            )
            raise OrchestrationIncident(
                "team is paused by a shared orchestration incident",
                failure=failure,
            )
        run_id = self._approved_run_id()
        if run_id is None or self._current_training_job_id(run_id) is not None:
            return
        score_path = self._score_path_for_run(run_id)
        if score_path is not None and score_path.is_file():
            return
        team_dir = os.environ.get("TEAM_DIR", "").strip()
        if team_dir and (
            Path(team_dir) / "submissions" / run_id / ".submitted"
        ).is_file():
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
        self._validate_protected_submission_files()
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
            feedback = build_failure_feedback(
                error,
                error_code="training_submission_timeout",
                stage="training_submission",
                retryable=True,
                public_summary="approved training submission wrapper timed out",
            )
            incident = OrchestrationIncident(
                str(feedback["summary"]), failure=feedback
            )
            self._publish_orchestration_incident(incident)
            raise incident from error
        job_id = completed.stdout.strip()
        if completed.returncode != 0 or not re.fullmatch(r"[0-9]+", job_id):
            failure_error = _retain_process_failure(
                error=RuntimeError(
                    f"training submission exit {completed.returncode}"
                ),
                error_code="training_submission_failed",
                stage="training_submission",
                public_summary=(
                    "approved training submission wrapper failed "
                    f"(exit {completed.returncode})"
                ),
            )
            incident = OrchestrationIncident(
                str(failure_error), failure=failure_error.feedback
            )
            self._publish_orchestration_incident(incident)
            raise incident
        receipt_job = self._current_training_job_id(run_id)
        if receipt_job != job_id:
            feedback = build_failure_feedback(
                RuntimeError("verified receipt missing"),
                error_code="training_receipt_missing",
                stage="training_submission",
                public_summary=(
                    "training submission did not publish its verified receipt"
                ),
            )
            incident = OrchestrationIncident(
                str(feedback["summary"]), failure=feedback
            )
            self._publish_orchestration_incident(incident)
            raise incident
        print(f"[Kimi] deterministically submitted approved training job {job_id}")

    @staticmethod
    def _autodata_enabled() -> bool:
        return os.getenv("AAR_AUTODATA", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _autodata_wait_required(self, output: dict[str, Any]) -> bool:
        """Whether the trusted host should poll instead of spending a model turn."""
        if self.completion_tool != "share_finding" or not self._autodata_enabled():
            return False
        if not self._owns_approved_run(output):
            return False
        run_id = self._approved_run_id()
        return run_id is not None and not self._autodata_handoff_ready(run_id)

    def _owns_approved_run(self, output: dict[str, Any]) -> bool:
        """Return whether this session may advance the current durable proposal."""
        return (
            self._submitted_proposal_in_output(output)
            and self._proposal_marker_changed_this_session()
        ) or self._resume_approved_proposal_enabled()

    @staticmethod
    def _autodata_stop_after_production() -> bool:
        return os.getenv("AAR_AUTODATA_STOP_AFTER", "").strip() == "production"

    @staticmethod
    def _autodata_stop_after_training_smoke() -> bool:
        return (
            os.getenv("AAR_AUTODATA_STOP_AFTER", "").strip()
            == "training_smoke"
        )

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
        timing = verification.get("timing")
        if not isinstance(timing, dict) or timing.get("schema") != (
            "aar.autodata.lifecycle-timing/v1"
        ):
            raise RuntimeError("verified production handoff has no lifecycle timing")
        timing_path = (
            Path(team_raw)
            / "autodata"
            / run_id
            / "autodata-lifecycle-timing.json"
        )
        cls._write_private_text(
            timing_path, json.dumps(timing, indent=2, sort_keys=True)
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
            "timing_report": str(timing_path),
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

    @classmethod
    def _complete_autodata_training_smoke_canary(cls, run_id: str) -> Path:
        """Verify full data consumption and one real optimizer step."""
        if not cls._autodata_stop_after_training_smoke():
            raise RuntimeError("AutoData training-smoke stop is not active")
        team_raw = os.getenv("TEAM_DIR", "").strip()
        if not team_raw:
            raise RuntimeError("TEAM_DIR is required for the training-smoke canary")
        team = Path(team_raw)
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
        timing = verification.get("timing")
        if not isinstance(timing, dict) or timing.get("schema") != (
            "aar.autodata.lifecycle-timing/v1"
        ):
            raise RuntimeError("verified production handoff has no lifecycle timing")
        timing_path = team / "autodata" / run_id / "autodata-lifecycle-timing.json"
        cls._write_private_text(
            timing_path, json.dumps(timing, indent=2, sort_keys=True)
        )

        job_id = cls._current_training_job_id(run_id)
        if job_id is None:
            raise RuntimeError("training-smoke canary has no training submission receipt")
        smoke_path = team / "method_smoke" / f"{run_id}.passed.json"
        try:
            smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("training-smoke result marker is unreadable") from error
        consumption = smoke.get("autodata_consumption")
        if (
            smoke.get("schema_version") != 1
            or smoke.get("status") != "passed"
            or smoke.get("run_id") != run_id
            or smoke.get("smoke_run") is not True
            or smoke.get("optimizer_steps") != 1
            or smoke.get("slurm_job_id") != job_id
            or not isinstance(consumption, dict)
            or consumption.get("run_id") != run_id
            or consumption.get("consumed_rows") != required_rows
            or consumption.get("required_rows") != required_rows
            or consumption.get("dataset_sha256") != verification.get("dataset_sha256")
            or consumption.get("production_execution_id")
            != verification.get("production_execution_id")
        ):
            raise RuntimeError(
                "training-smoke result does not prove exact AutoData consumption"
            )
        model_path_raw = smoke.get("model_path")
        weight_name = smoke.get("adapter_weight_file")
        if not isinstance(model_path_raw, str) or not isinstance(weight_name, str):
            raise RuntimeError("training-smoke result has no adapter identity")
        receipt_raw = consumption.get("consumption_receipt")
        if not isinstance(receipt_raw, str):
            raise RuntimeError("training-smoke result has no consumption receipt")
        phase_timings_raw = smoke.get("phase_timings")
        if not isinstance(phase_timings_raw, str):
            raise RuntimeError("training-smoke result has no phase timing artifact")
        receipt_candidate = Path(receipt_raw)
        if receipt_candidate.is_symlink():
            raise RuntimeError("training-smoke consumption receipt is unsafe")
        receipt_path = receipt_candidate.resolve(strict=True)
        phase_timings_path = Path(phase_timings_raw).resolve(strict=True)
        model_path = Path(model_path_raw).resolve(strict=True)
        team_root = team.resolve(strict=True)
        if (
            team_root not in model_path.parents
            or team_root not in receipt_path.parents
            or team_root not in phase_timings_path.parents
        ):
            raise RuntimeError(
                "training-smoke evidence is outside the team directory"
            )
        weight_path = (model_path / weight_name).resolve(strict=True)
        if model_path not in weight_path.parents or weight_path.stat().st_size <= 0:
            raise RuntimeError("training-smoke adapter weight file is empty or unsafe")

        marker = team / "autodata" / run_id / "training-smoke-canary-complete.json"
        payload = {
            "schema": "aar.autodata.training-smoke-canary-complete/v1",
            "run_id": run_id,
            "stop_after": "training_smoke",
            "required_accepted_rows": required_rows,
            "verification": verification,
            "timing_report": str(timing_path),
            "training": {
                "job_id": job_id,
                "optimizer_steps": 1,
                "consumed_rows": consumption["consumed_rows"],
                "consumption_receipt": str(receipt_path),
                "phase_timings": str(phase_timings_path),
                "method_smoke_marker": str(smoke_path),
                "model_path": str(model_path),
                "adapter_weight_file": weight_name,
                "adapter_weight_sha256": hashlib.sha256(
                    weight_path.read_bytes()
                ).hexdigest(),
            },
        }
        encoded = json.dumps(payload, indent=2, sort_keys=True)
        if marker.exists():
            try:
                existing = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError(
                    "existing training-smoke canary marker is unreadable"
                ) from error
            if existing != payload:
                raise RuntimeError(
                    "existing training-smoke canary marker does not match verification"
                )
        else:
            cls._write_private_text(marker, encoded)
        print(
            "[Kimi] verified AutoData training-smoke canary: "
            f"{required_rows} rows consumed; one optimizer step passed"
        )
        return marker

    @classmethod
    def _resume_approved_proposal_enabled(cls) -> bool:
        enabled = os.getenv(
            "AAR_RESUME_APPROVED_PROPOSAL", "0"
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not enabled:
            return False

        # Recovery is a one-run handoff, even though the chain process can host
        # many research sessions.  Permanently disarm the process-level flag as
        # soon as the retained run reaches either terminal outcome.  Merely
        # returning false is insufficient: a later proposal rejection replaces
        # the marker with one that has no run ID and would otherwise reactivate
        # recovery inside the same process.
        run_id = cls._approved_run_id()
        if run_id is None:
            return True
        if cls._finding_persisted_for_run(run_id) or (
            cls._current_training_failure() is not None
        ):
            os.environ["AAR_RESUME_APPROVED_PROPOSAL"] = "0"
            return False
        return True

    @staticmethod
    def _finding_persisted_for_run(run_id: str) -> bool:
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
    def _autodata_handoff_ready(run_id: str) -> bool:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
            return False
        team_dir = os.getenv("TEAM_DIR", "").strip()
        if not team_dir:
            return False
        run_root = Path(team_dir) / "autodata" / run_id
        handoff = run_root / "training-handoff.json"
        marker = run_root / "training-handoff.verified.json"
        handoff_present = handoff.exists() or handoff.is_symlink()
        marker_present = marker.exists() or marker.is_symlink()
        if not handoff_present and not marker_present:
            return False
        if not handoff_present or not marker_present:
            # The supervisor publishes the handoff before completing the exact
            # verifier.  Bound that legitimate visibility window; never turn a
            # permanently partial publication into a multi-hour host wait.
            visible = handoff if handoff_present else marker
            try:
                age = max(0.0, time.time() - visible.lstat().st_mtime)
                grace = float(
                    os.getenv("AAR_AUTODATA_HANDOFF_PUBLICATION_GRACE_SECONDS", "120")
                )
            except (OSError, ValueError) as error:
                raise _retain_process_failure(
                    error=error,
                    error_code="autodata_handoff_publication_invalid",
                    stage="autodata_handoff",
                    public_summary="AutoData handoff publication is invalid",
                ) from error
            if grace < 0:
                raise RuntimeError(
                    "AAR_AUTODATA_HANDOFF_PUBLICATION_GRACE_SECONDS must be nonnegative"
                )
            if handoff_present and not marker_present and age < grace:
                return False
            raise _retain_process_failure(
                error=RuntimeError("AutoData handoff publication is incomplete"),
                error_code="autodata_handoff_publication_incomplete",
                stage="autodata_handoff",
                public_summary="AutoData handoff publication did not complete",
            )
        if (
            handoff.is_symlink()
            or marker.is_symlink()
            or not handoff.is_file()
            or not marker.is_file()
        ):
            raise _retain_process_failure(
                error=RuntimeError("AutoData handoff publication is unsafe"),
                error_code="autodata_handoff_publication_invalid",
                stage="autodata_handoff",
                public_summary="AutoData handoff publication is invalid",
            )
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            digest = "sha256:" + hashlib.sha256(handoff.read_bytes()).hexdigest()
        except (OSError, json.JSONDecodeError) as error:
            raise _retain_process_failure(
                error=error,
                error_code="autodata_handoff_marker_invalid",
                stage="autodata_handoff",
                public_summary="AutoData verified handoff marker is invalid",
            ) from error
        expected = {
            "schema": "aar.autodata.training-handoff-verified/v1",
            "run_id": run_id,
            "training_handoff_sha256": digest,
            "meta_execution_id": value.get("meta_execution_id"),
            "production_execution_id": value.get("production_execution_id"),
        }
        valid_ids = all(
            isinstance(value.get(key), str)
            and re.fullmatch(r"exe_[0-9a-f]{32}", value[key]) is not None
            for key in ("meta_execution_id", "production_execution_id")
        )
        if value != expected or not valid_ids:
            raise _retain_process_failure(
                error=ValueError("verified handoff marker does not match its handoff"),
                error_code="autodata_handoff_marker_invalid",
                stage="autodata_handoff",
                public_summary="AutoData verified handoff marker is invalid",
            )
        return True

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
        if not self._autodata_enabled():
            return (
                task
                + "\n\nAUTOMATIC RESUME CONTEXT: This is the same already-approved "
                f"outer iteration with run_id={run_id}. Trusted orchestration owns "
                "training submission and score waiting. Do not restart literature "
                "review, author or edit a method, submit another proposal, invent a "
                "run ID, or resubmit training. Use the durable score for this exact "
                "run and complete the required share_finding checkpoint."
            )
        return task

    def _validate_protected_submission_files(self) -> None:
        """Verify submission infrastructure against Git before executing it."""
        for relative_path in PROTECTED_SUBMISSION_FILES:
            path = self.workspace / relative_path
            try:
                committed = subprocess.run(
                    ["git", "show", f"HEAD:{relative_path}"],
                    cwd=self.workspace,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                self._raise_orchestration_incident(
                    f"cannot verify protected file from Git: {relative_path}",
                    error_code="protected_file_verification_failed",
                )
            if committed.returncode != 0:
                self._raise_orchestration_incident(
                    f"cannot read protected file from Git: {relative_path}",
                    error_code="protected_file_git_read_failed",
                )
            try:
                actual = path.read_bytes()
            except OSError:
                self._raise_orchestration_incident(
                    f"cannot read protected file: {relative_path}",
                    error_code="protected_file_read_failed",
                )
            expected_hash = hashlib.sha256(committed.stdout).hexdigest()
            actual_hash = hashlib.sha256(actual).hexdigest()
            if actual_hash != expected_hash:
                self._raise_orchestration_incident(
                    "protected file hash mismatch: "
                    f"{relative_path} expected={expected_hash} actual={actual_hash}",
                    error_code="protected_file_hash_mismatch",
                )
            if path.suffix == ".sh":
                try:
                    syntax = subprocess.run(
                        ["bash", "-n", str(path)],
                        cwd=self.workspace,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    self._raise_orchestration_incident(
                        f"cannot syntax-check protected shell file: "
                        f"{relative_path}",
                        error_code="protected_file_syntax_check_failed",
                    )
                if syntax.returncode != 0:
                    self._raise_orchestration_incident(
                        f"protected shell syntax check failed: {relative_path}",
                        error_code="protected_file_syntax_invalid",
                    )

    def _raise_orchestration_incident(
        self,
        message: str,
        *,
        error_code: str = "orchestration_integrity_failed",
    ) -> NoReturn:
        feedback = build_failure_feedback(
            RuntimeError(message),
            error_code=error_code,
            stage="training_submission",
            public_summary=message,
        )
        incident = OrchestrationIncident(message, failure=feedback)
        self._publish_orchestration_incident(incident)
        raise incident

    def _publish_orchestration_incident(self, error: Exception) -> None:
        """Atomically publish a team-wide fail-stop marker for operators/peers."""
        team_dir_value = os.environ.get("TEAM_DIR", "").strip()
        if not team_dir_value:
            return
        try:
            team_dir = Path(team_dir_value)
            team_dir.mkdir(parents=True, exist_ok=True)
            marker = team_dir / ".orchestration_incident.json"
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            failure = error.failure if isinstance(error, OrchestrationIncident) else None
            if not isinstance(failure, dict):
                failure = build_failure_feedback(
                    error,
                    error_code="orchestration_incident",
                    stage="training_submission",
                    public_summary="shared orchestration incident",
                )
            payload = {
                "status": "paused",
                "stage": "training_submission",
                "error": failure["summary"],
                "failure": failure,
                "source_head": head.stdout.strip() if head.returncode == 0 else None,
                "chain": os.environ.get("IDEA_UID") or os.environ.get("IDEA_NAME"),
                "created_at": datetime.now().astimezone().isoformat(),
                "operator_action": (
                    "Repair and validate shared submission infrastructure, deploy "
                    "a new commit, then resume the team."
                ),
            }
            fd, temporary = tempfile.mkstemp(
                prefix=f".{marker.name}.", dir=team_dir, text=True
            )
            try:
                with os.fdopen(fd, "w") as handle:
                    json.dump(payload, handle, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, marker)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temporary)
        except (OSError, subprocess.SubprocessError):
            # The originating OrchestrationIncident must still escape and stop
            # this chain even if the shared filesystem cannot accept the marker.
            print(
                "[Kimi] WARNING: could not publish orchestration incident marker",
                file=sys.stderr,
            )

    def active_orchestration_incident(self) -> Optional[dict[str, Any]]:
        """Return this revision's shared incident, if another chain published one."""
        team_dir = os.environ.get("TEAM_DIR", "").strip()
        if not team_dir:
            return None
        try:
            payload = json.loads(
                (Path(team_dir) / ".orchestration_incident.json").read_text()
            )
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return payload
        marker_head = payload.get("source_head")
        if (
            head.returncode == 0
            and isinstance(marker_head, str)
            and marker_head
            and marker_head != head.stdout.strip()
        ):
            return None
        return payload

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
                raise FailureFeedbackError(failure)
            if time.monotonic() >= next_scheduler_check:
                failure = self._reconcile_terminal_training_job(run_id, job_id)
                if failure is not None:
                    validated = self._current_training_failure()
                    if validated is not None:
                        raise FailureFeedbackError(validated)
                    raise FailureFeedbackError(
                        build_failure_feedback(
                            RuntimeError("invalid training failure marker"),
                            error_code="training_failure_marker_invalid",
                            stage="training",
                            public_summary="training produced an invalid failure marker",
                        )
                    )
                next_scheduler_check = time.monotonic() + 30
            if time.monotonic() >= next_update:
                print(f"[Kimi] waiting for score from training job {job_id}")
                next_update = time.monotonic() + 60
            await asyncio.sleep(10)
        raise FailureFeedbackError(
            build_failure_feedback(
                TimeoutError("training score wait timed out"),
                error_code="training_result_timeout",
                stage="training",
                public_summary=(
                    "timed out waiting for the approved training score or failure marker"
                ),
            )
        )

    async def _wait_for_training_smoke_result(self) -> None:
        """Wait for the one-step marker without requiring an evaluator score."""
        run_id = self._approved_run_id()
        team_raw = os.getenv("TEAM_DIR", "").strip()
        if run_id is None or not team_raw:
            return
        job_id = self._current_training_job_id(run_id)
        if job_id is None:
            return
        marker = Path(team_raw) / "method_smoke" / f"{run_id}.passed.json"
        timeout_seconds = int(os.environ.get("AAR_KIMI_SCORE_WAIT_SECONDS", "10800"))
        deadline = time.monotonic() + timeout_seconds
        next_update = time.monotonic()
        next_scheduler_check = time.monotonic()
        completed_without_marker_since: float | None = None
        try:
            completion_grace = float(
                os.environ.get("AAR_TRAINING_MARKER_GRACE_SECONDS", "120")
            )
        except ValueError as error:
            raise RuntimeError(
                "AAR_TRAINING_MARKER_GRACE_SECONDS must be numeric"
            ) from error
        if completion_grace < 0:
            raise RuntimeError(
                "AAR_TRAINING_MARKER_GRACE_SECONDS must be nonnegative"
            )
        while time.monotonic() < deadline:
            if marker.is_file():
                print(f"[Kimi] one-step training smoke ready for approved run {run_id}")
                return
            failure = self._current_training_failure()
            if failure is not None:
                raise FailureFeedbackError(failure)
            if time.monotonic() >= next_scheduler_check:
                failure = self._reconcile_terminal_training_job(run_id, job_id)
                if failure is not None:
                    validated = self._current_training_failure()
                    if validated is not None:
                        raise FailureFeedbackError(validated)
                    raise FailureFeedbackError(
                        build_failure_feedback(
                            RuntimeError("invalid training failure marker"),
                            error_code="training_failure_marker_invalid",
                            stage="training",
                            public_summary="training produced an invalid failure marker",
                        )
                    )
                scheduler_result = self._slurm_job_result(job_id)
                if scheduler_result is not None and scheduler_result[0] == "COMPLETED":
                    now = time.monotonic()
                    if completed_without_marker_since is None:
                        completed_without_marker_since = now
                    if now - completed_without_marker_since >= completion_grace:
                        raise FailureFeedbackError(
                            build_failure_feedback(
                                RuntimeError(
                                    "training completed without its smoke marker"
                                ),
                                error_code="training_completed_without_smoke_marker",
                                stage="training",
                                public_summary=(
                                    "training completed but did not publish the required "
                                    "one-step smoke marker"
                                ),
                            )
                        )
                else:
                    completed_without_marker_since = None
                next_scheduler_check = time.monotonic() + 30
            if time.monotonic() >= next_update:
                print(f"[Kimi] waiting for one-step training job {job_id}")
                next_update = time.monotonic() + 60
            await asyncio.sleep(10)
        raise FailureFeedbackError(
            build_failure_feedback(
                TimeoutError("training smoke wait timed out"),
                error_code="training_smoke_timeout",
                stage="training",
                public_summary="timed out waiting for the one-step training marker",
            )
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
        if team_dir and os.getenv("AAR_RESEARCH_ENV_ISOLATION", "0") == "1":
            log_path = (
                Path(team_dir)
                / "secrets"
                / "failure-evidence"
                / f"train-{job_id}.out"
            )
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
                replace_invalid=True,
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
        if not isinstance(payload, dict):
            return None
        stage = payload.get("stage")
        error_code = payload.get("error_code")
        retryable = payload.get("retryable")
        if (
            payload.get("schema_version") != 2
            or payload.get("status") != "failed"
            or payload.get("run_id") != run_id
            or not isinstance(stage, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", stage) is None
            or not isinstance(error_code, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error_code) is None
            or not isinstance(retryable, bool)
        ):
            return None
        feedback = build_failure_feedback(
            RuntimeError(error_code),
            error_code=error_code,
            stage=stage,
            retryable=retryable,
            public_summary=f"{stage} failed ({error_code})",
        )
        feedback["run_id"] = run_id
        exception_type = payload.get("exception_type")
        if isinstance(exception_type, str) and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_.]{0,127}", exception_type
        ):
            feedback["exception_type"] = exception_type
        exit_code = payload.get("exit_code")
        if isinstance(exit_code, int) and not isinstance(exit_code, bool):
            feedback["exit_code"] = exit_code
        return feedback

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
        return failure

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
            "Use the typed code and retryability; operator evidence is intentionally "
            "not readable from the research sandbox. Record the cause in your chain memory, "
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
                if child.name == "config.toml":
                    config_text = child.read_text()
                    if self.auto_approve:
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
        config_path = overlay_home / "config.toml"
        if not config_path.exists():
            config_path.write_text(
                'defaultPermissionMode = "auto"\n' if self.auto_approve else ""
            )
        guard_command = shlex.join(
            [sys.executable, "-m", "aar.research_loop.kimi_write_guard"]
        )
        with config_path.open("a") as config:
            config.write(
                "\n[[hooks]]\n"
                'event = "PreToolUse"\n'
                'matcher = "^(Write|Edit)$"\n'
                f"command = {json.dumps(guard_command)}\n"
                "timeout = 5\n"
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
        if (
            not disable_thinking
            and not self.force_checkpoint_tools
            and not self.force_completion_tool_first_turn
        ):
            yield controller
            return

        upstream_base_url = env.get("KIMI_MODEL_BASE_URL", "")
        upstream_api_key = env.get("KIMI_MODEL_API_KEY", "")
        parsed = urlsplit(upstream_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(
                "Kimi request policy requires a valid KIMI_MODEL_BASE_URL"
            )
        if not upstream_api_key:
            raise RuntimeError(
                "Kimi request policy requires KIMI_MODEL_API_KEY"
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
