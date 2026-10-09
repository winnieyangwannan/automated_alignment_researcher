"""Kimi Code CLI adapter for the autonomous research loop."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import shlex
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
        max_continuations: int = 24,
        disallowed_tools: Optional[list[str]] = None,
        auto_approve: bool = False,
        force_checkpoint_tools: bool = False,
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
        self.auto_approve = auto_approve
        self.force_checkpoint_tools = force_checkpoint_tools

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
                    # Proposal markers persist across AutonomousAgentLoop sessions.
                    # Only the session that actually submitted the proposal may act
                    # on that marker; otherwise one failed run poisons every later
                    # session and burns the iteration budget without allowing a fix.
                    if self._submitted_proposal_in_output(output):
                        self._ensure_approved_training_submission()
                        await self._wait_for_training_result()
                        training_failure = self._current_training_failure()
                        approved_run_id = self._approved_run_id()
                        score_path = (
                            self._score_path_for_run(approved_run_id)
                            if approved_run_id is not None
                            else None
                        )
                        if training_failure is not None and not (
                            score_path is not None and score_path.is_file()
                        ):
                            raise RuntimeError(
                                "Kimi training failed closed: "
                                + json.dumps(training_failure, sort_keys=True)[:2000]
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
        approved_run_id = self._approved_run_id() if proposal_index >= 0 else None
        training_job_id = (
            self._current_training_job_id(approved_run_id)
            if approved_run_id is not None
            else None
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
                    "read. Do not emit prose or call evaluate_model."
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
            approved = self._proposal_is_approved()
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
        if "native Read tool exactly once" in prompt:
            return "Read"
        if "native Write tool exactly once" in prompt:
            return "Write"
        if "native Bash tool exactly once" in prompt:
            return "Bash"
        return None

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

    async def _wait_for_training_result(self) -> None:
        """Keep Kimi out of shell polling while the asynchronous job/evaluator runs."""
        if self.completion_tool != "share_finding":
            return
        run_id = self._approved_run_id()
        if run_id is None or self._current_training_job_id(run_id) is None:
            return
        score_path = self._score_path_for_run(run_id)
        if score_path is None or score_path.is_file():
            return
        timeout_seconds = int(os.environ.get("AAR_KIMI_SCORE_WAIT_SECONDS", "10800"))
        deadline = time.monotonic() + timeout_seconds
        next_update = time.monotonic()
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
            if time.monotonic() >= next_update:
                job_id = self._current_training_job_id(run_id)
                print(f"[Kimi] waiting for score from training job {job_id}")
                next_update = time.monotonic() + 60
            await asyncio.sleep(10)
        raise RuntimeError(
            f"timed out waiting for score or failure marker for approved run {run_id}"
        )

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
