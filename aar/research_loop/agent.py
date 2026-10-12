"""
Autonomous W2S research agent with Claude and Kimi backends.

Merges agent_loop, base_agent, and stop_conditions into a single file.
"""

import asyncio
import inspect
import json
import math
import os
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from aar.config import (
    WORKSPACE_DIR,
    S3_BUCKET,
    S3_IDEAS_PREFIX,
    LOGS_DIR,
    FULL_AUTO_MAX_RUNTIME_SECONDS,
    LOCAL_FINDINGS_DIR,
    FINDINGS_POLL_INTERVAL,
    TARGET_IDEA_FILE,
    DATASET_NAME,
    DATA_DIR,
    WEAK_MODEL,
    STRONG_MODEL,
    SERVER_URL,
    AAR_MODE,
)
from aar.phase_timing import phase
from aar.failure_feedback import (
    FailureFeedbackError,
    build_failure_feedback,
    feedback_from_exception,
    safe_failure_feedback_view,
)
from .chain_memory import ChainMemoryJournal
from .autodata_plugin import resolve_autodata_plugin
from .tools.server_api_tools import create_server_api_tools_server
from .tools.prior_work_tools import create_prior_work_tools_server
from .tools.findings_sync import FindingsSync
from .kimi_agent import KimiAgent, OrchestrationIncident


# These values belong to the operator-side integrity monitor and other trusted
# parent services. Claude Code (and therefore its Bash tool) must not inherit
# them.
_RESEARCH_CHILD_SECRET_NAMES = frozenset(
    {
        "HARNESS_ENV",
        "ANTHROPIC_API_KEY",
        "ANT_high_prio_API",
        "ANT_API_KEY",
        "MODEL_API_KEY",
        "LLAMA_API_KEY",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "OAI_API",
        "OPENAI_API_KEY",
        "AAR_MONITOR_MODEL_API_KEY",
        "AAR_MONITOR_ANTHROPIC_API_KEY",
        "AAR_RUN8_EXECSIDECAR_TOKEN_FILE",
        "AAR_RUN8_ADAPTER_TOKEN_FILE",
        "AAR_RUN8_BROKER_TOKEN_FILE",
        "AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE",
        "AAR_AUTODATA_MODEL_ENV_FILE",
        "AAR_AUTODATA_APPROVAL_PRIVATE_KEY",
        "AAR_KIMI_PROXY_INFO",
    }
)


def _is_research_child_secret_name(name: str) -> bool:
    """Return whether an environment entry is credential material/reference."""
    upper = name.upper()
    return (
        upper in _RESEARCH_CHILD_SECRET_NAMES
        or upper.endswith("_API_KEY")
        or upper.endswith("_TOKEN")
        or upper.endswith("_TOKEN_FILE")
        or upper.endswith("_SECRET")
        or upper.endswith("_SECRET_FILE")
        or "CREDENTIAL" in upper
    )


@contextmanager
def _sanitized_research_subprocess_environment():
    """Temporarily remove secrets while the SDK spawns Claude Code.

    Claude Agent SDK merges ``ClaudeAgentOptions.env`` over ``os.environ``;
    passing a smaller mapping therefore does *not* isolate the child.  The SDK
    subprocess is created by ``ClaudeSDKClient.__aenter__``, so temporarily
    removing sensitive entries during that operation gives the child a clean
    environment, then restores the trusted Python parent's access.
    """
    removed = {
        name: value
        for name, value in list(os.environ.items())
        if _is_research_child_secret_name(name)
    }
    for name in removed:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        os.environ.update(removed)


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _format_baselines() -> str:
    """Render the measured base-model baselines into a prompt-ready block, read
    from the authoritative baselines.json (so the prompt never carries stale
    hardcoded numbers — the bug that broke the gsm8k floor). Empty if unavailable."""
    import os
    path = os.getenv("BASELINES_PATH")
    if not path:
        try:
            from aar.config import HARNESS_RUNS_DIR
            path = os.path.join(HARNESS_RUNS_DIR, "baselines.json")
        except Exception:
            return ""
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        return ""
    # HELD-OUT benchmarks (the axis's generalization set, e.g. sycon_fp) are INVISIBLE
    # to the AAR — never render them in the prompt, or the AAR could optimize toward
    # them. The launcher sets HELD_OUT_BENCH (comma-sep) for the axis's held-out set.
    held = {b.strip() for b in os.getenv("HELD_OUT_BENCH", "").split(",") if b.strip()}
    lines = []
    for name, d in data.items():
        if name in held:
            continue
        b = d.get("baseline")
        fl = d.get("floor")
        s = f"    - `{name}`: base model scores **{b}**"
        if fl is not None:
            s += f"  — capability floor **{fl}** (your method's CI must not fall clearly below this)"
        lines.append(s)
    return "\n".join(lines)


def resolve_prompt(template_path: str | Path, output_path: str | Path) -> str:
    """Render Jinja2 prompt template with config variables."""
    from jinja2 import Template

    template_path = Path(template_path)
    output_path = Path(output_path)

    with open(template_path, 'r') as f:
        template = Template(f.read())

    target_idea_content = ""
    if Path(TARGET_IDEA_FILE).exists():
        with open(TARGET_IDEA_FILE, 'r') as f:
            try:
                idea_data = json.load(f)
                target_idea_content = idea_data.get("Description", json.dumps(idea_data, indent=2))
            except json.JSONDecodeError:
                target_idea_content = f.read()
    else:
        print(f"WARNING: Target idea file not found: {TARGET_IDEA_FILE}")

    local_mode = os.getenv("LOCAL_MODE", "false").lower() in ("1", "true", "yes")
    autodata = os.getenv("AAR_AUTODATA", "0").lower() in ("1", "true", "yes")

    # Generalized harness vars (suite/target) alongside the legacy W2S ones, so
    # either prompt template renders.
    from aar.config import SUITE_NAME, TARGET_MODEL
    meta_secure_web = os.getenv("AAR_WEB_MODE", "native_web") == "meta_secure"
    paper_search_helper = str(
        (Path(WORKSPACE_DIR) / "scripts" / "aar-paper-search").resolve()
    )
    content = template.render(
        workspace_dir=WORKSPACE_DIR,
        dataset_name=DATASET_NAME,
        data_dir=DATA_DIR,
        weak_model=WEAK_MODEL,
        strong_model=STRONG_MODEL,
        suite_name=SUITE_NAME,
        # Per-axis (swappable via launcher env) — keeps the prompt axis-agnostic.
        safety_property=os.getenv("SAFETY_PROPERTY", SUITE_NAME),
        objective=os.getenv("SAFETY_OBJECTIVE", f"improve {SUITE_NAME}"),
        # OPT-IN full-observability briefing (2026-06-21): when BENCHMARK_BRIEF_FILE is set, its contents
        # (a detailed explanation of the scored benchmarks + metrics + scoring) render into the prompt.
        # EMPTY by default -> isolated runs are unchanged (D2 preserved). Used for the privacy
        # observability experiment; pairs with the per-iteration score decomposition (BenchmarkScore.extra).
        benchmark_brief=(open(os.environ["BENCHMARK_BRIEF_FILE"]).read()
                         if os.getenv("BENCHMARK_BRIEF_FILE") and os.path.exists(os.environ["BENCHMARK_BRIEF_FILE"])
                         else ""),
        seed_method=os.getenv("SEED_METHOD", ""),   # axis's reference seed idea dir (optional)
        target_model=TARGET_MODEL,
        target_model_path=os.getenv("TARGET_MODEL_PATH", TARGET_MODEL),
        target_thinking=os.getenv("AAR_TARGET_ENABLE_THINKING", "0").lower()
        in ("1", "true", "yes"),
        require_adapter=os.getenv("AAR_REQUIRE_ADAPTER", "0").lower()
        in ("1", "true", "yes"),
        method_train_minutes=int(os.getenv("AAR_METHOD_TRAIN_MINUTES", "30")),
        serve_v2_deployment_dir=os.getenv("AAR_SERVE_V2_DEPLOYMENT_DIR", ""),
        serve_v2_model=os.getenv("AAR_SERVE_V2_MODEL", ""),
        s3_bucket=S3_BUCKET,
        s3_ideas_prefix=S3_IDEAS_PREFIX,
        logs_dir=LOGS_DIR,
        # Per-chain memory file + chain id (parallel chains must NOT share an
        # AGENT_LOG or a method-dir namespace). agent_log_path is seeded by
        # slurm_aar_chain.sh with an explicit "iteration 1, no history" stub.
        agent_log_path=os.getenv("AAR_AGENT_LOG_PATH", f"{LOGS_DIR}/AGENT_LOG.md"),
        chain_id=(re.sub(r"[^A-Za-z0-9]+", "_", os.getenv("IDEA_NAME", "chain")).strip("_") or "chain"),
        # Decoupled (GPU-less agent) mode: the chain holds no GPU, so the agent must
        # train via a separate low-QoS job. Default false => original inline-capable prompt.
        no_local_gpu=os.getenv("AAR_NO_LOCAL_GPU", "false").lower() in ("1", "true", "yes"),
        server_url=SERVER_URL,
        aar_mode=str(AAR_MODE).lower(),
        local_mode=str(local_mode).lower(),
        target_idea_content=target_idea_content,
        baselines_table=_format_baselines(),
        meta_secure_web=meta_secure_web,
        paper_search_helper=paper_search_helper,
        autodata=autodata,
        autodata_sha=os.getenv("AAR_AUTODATA_SHA", ""),
        autodata_production_rows=int(
            os.getenv("AAR_AUTODATA_PRODUCTION_ROWS", "1000")
        ),
        autodata_production_initial_tasks=int(
            os.getenv("AAR_AUTODATA_PRODUCTION_INITIAL_TASKS", "1250")
        ),
        autodata_production_min_success_fraction=float(
            os.getenv("AAR_AUTODATA_PRODUCTION_MIN_SUCCESS_FRACTION", "0.95")
        ),
        autodata_stage_timeout_policy=os.getenv(
            "AAR_AUTODATA_STAGE_TIMEOUT_POLICY", "enforce"
        ),
        autodata_native_schema_wall_seconds=int(
            os.getenv("AAR_AUTODATA_NATIVE_SCHEMA_WALL_SECONDS", "0")
        ),
    )

    with open(output_path, 'w') as f:
        f.write(content)

    return content


# ---------------------------------------------------------------------------
# Stop condition (just timeout)
# ---------------------------------------------------------------------------

class StopReason(Enum):
    TIMEOUT = "timeout"
    USER_INTERRUPT = "user_interrupt"


class _StopChecker:
    """Simple timeout-only stop checker."""

    def __init__(self, max_runtime: float):
        self.max_runtime = max_runtime
        self.start_time = time.time()
        self.consecutive_errors = 0

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

    def check(self) -> Optional[StopReason]:
        if self.elapsed_time >= self.max_runtime:
            return StopReason.TIMEOUT
        return None

    def record_success(self):
        self.consecutive_errors = 0

    def record_error(self):
        self.consecutive_errors += 1


# ---------------------------------------------------------------------------
# Agent result
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    success: bool
    output: Dict[str, Any]
    duration: float
    iteration_count: int
    error: Optional[str] = None
    failure: Optional[Dict[str, Any]] = None


def _is_overloaded(err: object) -> bool:
    """True if an exception/message is an Anthropic API 529 'Overloaded' error.

    These are transient capacity errors — the right response is to wait and
    retry, not to abandon the iteration. We match on the text so it works
    whether the SDK raises a typed error or surfaces it as a generic message.
    """
    s = str(err).lower()
    return "overloaded" in s or "529" in s


# How long to wait, and how many times to retry, when the API is overloaded.
# Defaults: wait 10 minutes, up to 6 times (~1h of riding out an outage) before
# giving up on the session. Override via env for tests / different SLAs.
OVERLOADED_WAIT_SECONDS = int(os.getenv("OVERLOADED_WAIT_SECONDS", "600"))
OVERLOADED_MAX_RETRIES = int(os.getenv("OVERLOADED_MAX_RETRIES", "6"))


def _agent_sdk_supports_option(name: str) -> bool:
    """Return whether this installed Agent SDK accepts an option keyword.

    Older Agent SDK releases did not accept the newer ``thinking`` and
    ``effort`` keywords. Inspecting the constructor keeps this helper usable in
    portable environments even though this project pins a newer SDK.
    """
    try:
        parameters = inspect.signature(ClaudeAgentOptions).parameters
    except (TypeError, ValueError):
        annotations = getattr(ClaudeAgentOptions, "__annotations__", {})
        return name in annotations
    return name in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _add_supported_reasoning_options(options: Dict[str, Any]) -> None:
    """Add optional reasoning controls understood by the installed SDK."""
    if _agent_sdk_supports_option("thinking"):
        options["thinking"] = {"type": "adaptive", "display": "summarized"}
    if _agent_sdk_supports_option("effort"):
        options["effort"] = os.getenv("AAR_EFFORT", "max")


def _add_supported_budget_options(options: Dict[str, Any]) -> None:
    """Apply an optional hard Claude CLI budget to one agent session."""
    raw = os.getenv("AAR_CLAUDE_SESSION_BUDGET_USD", "").strip()
    if not raw:
        return
    try:
        budget = float(raw)
    except ValueError as error:
        raise ValueError("AAR_CLAUDE_SESSION_BUDGET_USD must be positive") from error
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("AAR_CLAUDE_SESSION_BUDGET_USD must be positive")
    if not _agent_sdk_supports_option("max_budget_usd"):
        raise RuntimeError("installed Claude Agent SDK cannot enforce max_budget_usd")
    options["max_budget_usd"] = budget


# ---------------------------------------------------------------------------
# Base agent (wraps Claude Agent SDK)
# ---------------------------------------------------------------------------

class BaseAgent:
    """Wraps ClaudeSDKClient for research tasks."""

    def __init__(
        self,
        name: str,
        allowed_tools: List[str],
        workspace: Path,
        mcp_servers: Dict[str, Any],
        model: str = os.getenv("AAR_AGENT_MODEL", "claude-opus-4-8"),
        permission_mode: str = "bypassPermissions",
        cli_path: Optional[str] = None,
        message_callback: Optional[Callable] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[str]] = None,
        setting_sources: Optional[List[str]] = None,
        strict_mcp_config: Optional[bool] = None,
        plugins: Optional[List[Dict[str, str]]] = None,
        skills: Optional[List[str]] = None,
        progress_timeout_seconds: Optional[float] = None,
    ):
        self.name = name
        self.allowed_tools = allowed_tools
        self.workspace = workspace
        self.mcp_servers = mcp_servers
        self.model = model
        self.permission_mode = permission_mode
        self.cli_path = cli_path
        self.message_callback = message_callback
        self.system_prompt = system_prompt
        self.tools = tools
        self.setting_sources = setting_sources
        self.strict_mcp_config = strict_mcp_config
        self.plugins = plugins
        self.skills = skills
        if progress_timeout_seconds is None:
            raw_timeout = os.getenv("AAR_AGENT_TURN_TIMEOUT_SECONDS", "").strip()
            progress_timeout_seconds = float(raw_timeout) if raw_timeout else None
        if progress_timeout_seconds is not None and progress_timeout_seconds <= 0:
            raise ValueError("Claude progress timeout must be positive")
        self.progress_timeout_seconds = progress_timeout_seconds

    def _build_options_dict(self) -> Dict[str, Any]:
        """Build SDK options, including restrictive knobs only when requested."""
        options: Dict[str, Any] = {
            "allowed_tools": self.allowed_tools,
            "system_prompt": self.system_prompt,
            "permission_mode": self.permission_mode,
            "cwd": str(self.workspace),
            "model": self.model,
            "mcp_servers": self.mcp_servers,
            "betas": ["context-1m-2025-08-07"],
        }
        if self.tools is not None:
            options["tools"] = self.tools
        if self.setting_sources is not None:
            options["setting_sources"] = self.setting_sources
        if self.strict_mcp_config is not None:
            options["strict_mcp_config"] = self.strict_mcp_config
        if self.plugins is not None:
            if not _agent_sdk_supports_option("plugins"):
                raise RuntimeError("installed Claude Agent SDK does not support plugins")
            options["plugins"] = self.plugins
        if self.skills is not None:
            if not _agent_sdk_supports_option("skills"):
                raise RuntimeError("installed Claude Agent SDK does not support skills")
            options["skills"] = self.skills
        _add_supported_reasoning_options(options)
        _add_supported_budget_options(options)
        if self.cli_path:
            options["cli_path"] = self.cli_path
        return options

    async def execute(self, task: str) -> AgentResult:
        """Execute agent task. Returns AgentResult.

        If the API returns a 529 'Overloaded' error, wait OVERLOADED_WAIT_SECONDS
        (default 10 min) and retry the same session, up to OVERLOADED_MAX_RETRIES
        times — a capacity blip shouldn't burn an iteration or kill the chain.
        """
        start_time = time.time()
        overloaded_retries = 0

        while True:
            try:
                return await self._execute_once(task, start_time)
            except Exception as e:
                overloaded = _is_overloaded(e)
                if overloaded and overloaded_retries < OVERLOADED_MAX_RETRIES:
                    overloaded_retries += 1
                    print(
                        f"[{self.name}] API overloaded (529). Waiting "
                        f"{OVERLOADED_WAIT_SECONDS}s before retry "
                        f"{overloaded_retries}/{OVERLOADED_MAX_RETRIES}..."
                    )
                    await asyncio.sleep(OVERLOADED_WAIT_SECONDS)
                    continue
                progress_timeout = isinstance(e, TimeoutError)
                error_code = (
                    "claude_model_overloaded"
                    if overloaded
                    else "claude_progress_timeout"
                    if progress_timeout
                    else "claude_agent_failed"
                )
                feedback = build_failure_feedback(
                    e,
                    error_code=error_code,
                    stage="research_session",
                    retryable=overloaded,
                    public_summary=(
                        "Claude model service is overloaded"
                        if overloaded
                        else "Claude research session stopped after no substantive progress"
                        if progress_timeout
                        else "Claude research session failed"
                    ),
                )
                return AgentResult(
                    success=False,
                    output={},
                    duration=time.time() - start_time,
                    iteration_count=0,
                    error=str(feedback["summary"]),
                    failure=feedback,
                )

    async def _execute_once(self, task: str, start_time: float) -> AgentResult:
        """One attempt at running the session (no retry). Raises on API error so
        execute() can decide whether to retry (529) or give up."""
        iteration_count = 0
        messages = []

        if True:
            options = ClaudeAgentOptions(**self._build_options_dict())

            # Trusted parent services may need purpose-specific credentials,
            # while Claude Code and its Bash descendants must not receive them.
            # Restrict only the subprocess-spawn window; after __aenter__,
            # restoring the parent does not change the child's environment.
            with _sanitized_research_subprocess_environment():
                client_context = ClaudeSDKClient(options=options)
                client = await client_context.__aenter__()
            try:
                await client.query(task)
                result_message = None

                response = client.receive_response().__aiter__()
                last_progress = time.monotonic()
                while True:
                    timeout = None
                    if self.progress_timeout_seconds is not None:
                        timeout = max(
                            0.0,
                            self.progress_timeout_seconds
                            - (time.monotonic() - last_progress),
                        )
                    try:
                        message = await asyncio.wait_for(
                            response.__anext__(), timeout=timeout
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError as error:
                        raise TimeoutError(
                            "Claude research session produced no substantive "
                            f"progress for {self.progress_timeout_seconds:g} seconds"
                        ) from error

                    messages.append(message)

                    # SystemMessage heartbeats prove that Claude Code is alive,
                    # but do not show substantive research or tool progress.
                    if type(message).__name__ != "SystemMessage":
                        last_progress = time.monotonic()

                    # Log
                    log_msg = self._format_message(message)
                    if log_msg:
                        print(log_msg)

                    if self.message_callback:
                        self.message_callback(message)

                    if isinstance(message, ResultMessage):
                        result_message = message
                        break

                    if isinstance(message, AssistantMessage):
                        for content in message.content:
                            if isinstance(content, ToolUseBlock):
                                iteration_count += 1

                if result_message is None:
                    raise RuntimeError("Claude Agent SDK ended without a result message")
                if getattr(result_message, "is_error", False):
                    detail = getattr(result_message, "result", None) or "unknown SDK error"
                    raise RuntimeError(f"Claude Agent SDK returned an error result: {detail}")

                return AgentResult(
                    success=True,
                    output=self._extract_output(messages),
                    duration=time.time() - start_time,
                    iteration_count=iteration_count,
                )
            finally:
                await client_context.__aexit__(None, None, None)

    def _format_message(self, message) -> Optional[str]:
        ts = datetime.now().strftime("%H:%M:%S")
        if isinstance(message, AssistantMessage):
            parts = []
            for content in message.content:
                if isinstance(content, TextBlock):
                    parts.append(f"[{ts}] [{self.name}] {content.text[:200]}")
                elif isinstance(content, ToolUseBlock):
                    tool_input = content.input or {}
                    detail = ""
                    if content.name == "Bash":
                        detail = f" {tool_input.get('command', '')[:100]}"
                    elif content.name in ("Read", "Write", "Edit"):
                        detail = f" {tool_input.get('file_path', '')}"
                    parts.append(f"[{ts}] [{self.name}] -> {content.name}{detail}")
            return "\n".join(parts) if parts else None
        elif isinstance(message, ResultMessage):
            return f"[{ts}] [{self.name}] Done"
        return None

    def _extract_output(self, messages) -> Dict[str, Any]:
        output = {"text_outputs": [], "tool_uses": []}
        for msg in messages:
            if isinstance(msg, AssistantMessage):
                for content in msg.content:
                    if isinstance(content, TextBlock):
                        output["text_outputs"].append(content.text)
                    elif isinstance(content, ToolUseBlock):
                        output["tool_uses"].append({"tool": content.name, "input": content.input})
            if isinstance(msg, ResultMessage):
                output["result_message"] = msg.result
        return output


# ---------------------------------------------------------------------------
# Main autonomous loop
# ---------------------------------------------------------------------------

class AutonomousAgentLoop:
    """
    Main agent loop for autonomous W2S research.

    Each iteration is a fresh agent session. Agent reads/writes findings.json
    directly. Only stop condition: timeout.
    """

    def __init__(
        self,
        idea_uid: str,
        idea_name: str,
        workspace: Optional[Path] = None,
        max_runtime_seconds: Optional[int] = None,
        max_iterations: Optional[int] = None,
        logs_dir: Optional[Path] = None,
        s3_bucket: Optional[str] = None,
        model: Optional[str] = None,
        backend: str = os.getenv("AAR_AGENT_BACKEND", "claude"),
        local_mode: bool = False,
    ):
        if not idea_uid:
            raise ValueError("idea_uid is required")

        self.idea_uid = idea_uid
        self.idea_name = idea_name
        self.local_mode = local_mode
        self.run_id = os.getenv("RUN_ID") or str(uuid.uuid4())
        os.environ.setdefault("RUN_ID", self.run_id)

        self.workspace = Path(workspace) if workspace else Path(WORKSPACE_DIR)
        self.logs_dir = Path(logs_dir) if logs_dir else Path(LOGS_DIR)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.findings_path = self.logs_dir.parent / "findings.json"

        # The editable AGENT_LOG remains model scratch space.  This separate
        # host-owned journal is reconstructed from durable public lifecycle
        # artifacts and is injected identically for Claude and Kimi sessions.
        self.chain_memory = ChainMemoryJournal.from_environment(
            chain_id=self.idea_name,
            idea_uid=self.idea_uid,
            fallback_team_dir=self.logs_dir.parent,
        )

        self.max_runtime_seconds = max_runtime_seconds or FULL_AUTO_MAX_RUNTIME_SECONDS
        # Cap on number of iterations (= sessions). env MAX_ITERATIONS or arg; None = unbounded.
        self.max_iterations = max_iterations if max_iterations is not None else (
            int(os.getenv("MAX_ITERATIONS")) if os.getenv("MAX_ITERATIONS") else None)
        self.s3_bucket = s3_bucket or S3_BUCKET
        self.s3_prefix = f"{S3_IDEAS_PREFIX}{idea_uid}/{self.run_id}/"
        self.backend = backend.strip().lower()
        if self.backend not in ("claude", "kimi"):
            raise ValueError("backend must be 'claude' or 'kimi'")
        self.model = model or (
            os.getenv("AAR_AGENT_MODEL", "claude-opus-4-8")
            if self.backend == "claude"
            else os.getenv("KIMI_AGENT_MODEL")
        )

        self.stop_checker = _StopChecker(max_runtime=self.max_runtime_seconds)

        # Claude uses SDK-local MCP servers. Kimi starts standard stdio MCP
        # bridges in its isolated CLI configuration.
        self.mcp_servers = {}
        if self.backend == "claude":
            try:
                self.mcp_servers["server-api-tools"] = create_server_api_tools_server()
            except Exception:
                print("[Init] Warning: server API tools unavailable")
            if not local_mode:
                try:
                    self.mcp_servers["prior-work-tools"] = create_prior_work_tools_server()
                except Exception:
                    print("[Init] Warning: prior work tools unavailable")
        # AutoData is an upstream local Claude plugin. AAR verifies the pinned
        # checkout, then lets the agent use the plugin's own skill and CLI.
        # No AAR-specific AutoData MCP server or lifecycle wrapper is created.
        self.autodata_plugin = resolve_autodata_plugin()

        # Findings sync: disabled in local mode (no other workers)
        self.findings_sync = None
        if not local_mode:
            self.findings_sync = FindingsSync(
                findings_dir=Path(LOCAL_FINDINGS_DIR),
                poll_interval=FINDINGS_POLL_INTERVAL,
            )

        self.session_count = 0
        self._prompt: Optional[str] = None

    def _get_prompt(self) -> str:
        if self._prompt is None:
            # PROMPT_TEMPLATE selects the system prompt (e.g. prompt_safety.jinja2,
            # the generic axis-agnostic submit-model prompt; prompt.jinja2 for legacy W2S).
            tmpl_name = os.getenv("PROMPT_TEMPLATE", "prompt.jinja2")
            template_path = self.workspace / "aar" / "research_loop" / tmpl_name
            if not template_path.exists():
                raise FileNotFoundError(f"Prompt template not found: {template_path}")
            resolved_path = self.logs_dir / "prompt_resolved.md"
            self._prompt = resolve_prompt(template_path, resolved_path)
        return self._prompt

    def _create_agent(self, session_id: str, message_callback=None):
        meta_secure_web = os.getenv("AAR_WEB_MODE", "native_web") == "meta_secure"
        autodata_plugin = getattr(self, "autodata_plugin", None)
        if getattr(self, "backend", "claude") == "kimi":
            autodata_stop_after = os.getenv("AAR_AUTODATA_STOP_AFTER", "").strip()
            if autodata_stop_after == "production":
                kimi_system_prompt = (
                    "You are running a production-only AutoData canary "
                    "noninteractively. Complete the approved target-aware AutoData "
                    "meta-optimization and production workflow using tools now. The "
                    "iteration is complete when the verified production handoff "
                    "contains the configured accepted-row target. Do not submit "
                    "training, wait for a score, evaluate an adapter, or call "
                    "share_finding. Never end with a statement of future intent such "
                    "as 'let me' or 'next I will'. During initial discovery, call "
                    "get_literature exactly once with an empty input."
                )
            elif autodata_stop_after == "training_smoke":
                kimi_system_prompt = (
                    "You are running a data-to-training AutoData canary "
                    "noninteractively. Complete the approved target-aware AutoData "
                    "meta-optimization and production workflow, submit the approved "
                    "method to the trusted training wrapper, and wait for its real-GPU "
                    "one-optimizer-step smoke result. The iteration is complete only "
                    "when all configured production rows were consumed and a loadable "
                    "non-empty PEFT adapter was saved. Do not run full training, start "
                    "an evaluator, wait for a score, evaluate an adapter, or call "
                    "share_finding. Never end with a statement of future intent such "
                    "as 'let me' or 'next I will'. During initial discovery, call "
                    "get_literature exactly once with an empty input."
                )
            else:
                kimi_system_prompt = (
                    "You are running noninteractively. Complete the entire requested "
                    "research iteration using tools now. Never end with a statement of "
                    "future intent such as 'let me' or 'next I will'. The iteration is "
                    "complete only after a real score result is available and "
                    "share_finding succeeds. Follow the resolved research prompt's "
                    "training/evaluation flow exactly; when it says the asynchronous "
                    "training job produces the score, do not call evaluate_model. "
                    "During initial discovery, call get_literature exactly once with an "
                    "empty input to obtain compact summaries; do not request multiple "
                    "dimensions in parallel. If essential, make at most one focused "
                    "literature follow-up after selecting a method direction."
                )
            if meta_secure_web:
                kimi_system_prompt += (
                    " Use the repository's bounded arXiv helper for internet research. "
                    "Do not use curl, wget, or arbitrary network URLs."
                )
            if autodata_plugin is not None:
                kimi_system_prompt += (
                    " Before any AutoData work, load the `autodata` skill from "
                    "the operator-pinned skill directory. In Kimi, `autodata` is "
                    "the same skill that Claude identifies as "
                    "`autodata:autodata`; follow the loaded skill and its references."
                )
            return KimiAgent(
                name=f"autonomous-{session_id}",
                workspace=self.workspace,
                model=self.model,
                cli_path=os.getenv("KIMI_CLI_PATH") or shutil.which("kimi"),
                message_callback=message_callback,
                system_prompt=kimi_system_prompt,
                skill_dirs=(
                    [autodata_plugin.root / "skills"]
                    if autodata_plugin is not None
                    else None
                ),
                include_prior_work=not self.local_mode,
                completion_tool="share_finding",
                auto_approve=True,
                force_checkpoint_tools=True,
                disallowed_tools=[
                    "CreateGoal",
                    "UpdateGoal",
                    "SetGoalBudget",
                    "TodoList",
                    "WaitFor",
                    "Agent",
                    "AgentSwarm",
                ],
            )

        allowed_tools = [
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
            "mcp__server-api-tools__evaluate_model",
            "mcp__server-api-tools__evaluate_predictions",
            "mcp__server-api-tools__share_finding",
            "mcp__server-api-tools__get_leaderboard",
            "mcp__server-api-tools__get_literature",
            "mcp__server-api-tools__share_literature",
            "mcp__server-api-tools__submit_idea_proposal",
            "mcp__server-api-tools__review_autodata_action",
        ]
        if meta_secure_web:
            helper = (self.workspace / "scripts" / "aar-paper-search").resolve()
            allowed_tools.append(f"Bash({helper} *)")
        else:
            allowed_tools.extend(["WebSearch", "WebFetch"])
        if not self.local_mode:
            allowed_tools.append("mcp__prior-work-tools__download_snapshot")

        system_parts = []
        if meta_secure_web:
            system_parts.append(
                "Use the repository's bounded arXiv helper for internet research. "
                "Do not use curl, wget, or arbitrary network URLs."
            )
        if autodata_plugin is not None:
            system_parts.append(
                "Load the autodata:autodata skill before any AutoData work. "
                "Use only the native CLI wrapper shipped by that plugin; no "
                "AAR-specific AutoData MCP interface exists. Keep all state, "
                "workspaces, and exports below the writable run directory."
            )
            if os.getenv("AAR_AUTODATA_LIFECYCLE_SUPERVISED", "0").lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                system_parts.append(
                    "The orchestration-owned AutoData lifecycle supervisor is the "
                    "only process allowed to call workspace step or execution step. "
                    "Never launch a stepper, detached controller, or direct step call. "
                    "Create meta and production executions only through "
                    "scripts/autodata_lifecycle_supervisor.py create-execution; "
                    "inspect its --help for required paths. This command derives a "
                    "stable content-bound idempotency key, registers the canonical "
                    "execution, and reuses an equivalent active or completed execution. "
                    "Never add a retry/version suffix to an execution idempotency key."
                )

        return BaseAgent(
            name=f"autonomous-{session_id}",
            allowed_tools=allowed_tools,
            workspace=self.workspace,
            mcp_servers=self.mcp_servers,
            model=self.model,
            cli_path=os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude"),
            message_callback=message_callback,
            permission_mode="dontAsk" if meta_secure_web else "bypassPermissions",
            system_prompt="\n\n".join(system_parts) or None,
            tools=["Skill", "Bash", "Read", "Write", "Edit", "Glob", "Grep"]
            if meta_secure_web else None,
            setting_sources=[] if meta_secure_web else ["project"],
            strict_mcp_config=True if meta_secure_web else None,
            plugins=(
                [autodata_plugin.sdk_config()]
                if autodata_plugin is not None
                else None
            ),
            skills=["autodata:autodata"] if autodata_plugin is not None else None,
        )

    def _ensure_approved_autodata_workspace(self) -> None:
        """Resume proposal-to-workspace bootstrap before either model backend starts."""
        if os.getenv("AAR_AUTODATA", "0").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return
        from aar.research_loop.autodata_bootstrap import ensure_workspace
        from aar.research_loop.tools.server_api_tools import (
            _atomic_json_write,
            _proposal_approved,
            _proposal_marker_path,
            ensure_proposal_journal_receipt,
        )

        marker_path = _proposal_marker_path()
        if not marker_path.is_file():
            return
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(marker, dict) or marker.get("approved") is not True:
            return
        if marker.get("journaled") is not True:
            recovered = ensure_proposal_journal_receipt(
                marker_path,
                team_dir=os.getenv("TEAM_DIR", ""),
                chain_id=self.idea_name,
                idea_uid=self.idea_uid,
                allow_backfill=False,
                mark_journaled=True,
            )
            if not recovered:
                raise FailureFeedbackError(
                    build_failure_feedback(
                        RuntimeError("durable proposal journal event is missing"),
                        error_code="proposal_journal_failed",
                        stage="proposal_submission",
                        retryable=False,
                        public_summary="host-owned proposal journal update failed",
                    )
                )
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("execution_ready") is True:
            approved, reason = _proposal_approved()
            if not approved:
                print(f"[AutoData bootstrap] proposal not resumable: {reason}")
                return
        identity = (
            marker.get("run_id"),
            marker.get("idea_name"),
            marker.get("code_hash"),
        )
        if not all(isinstance(value, str) and value for value in identity):
            raise RuntimeError("approved proposal lacks AutoData bootstrap identity")
        try:
            result = ensure_workspace(
                run_id=identity[0],
                idea_name=identity[1],
                code_hash=identity[2],
            )
        except Exception as error:
            failure = feedback_from_exception(
                error,
                error_code="autodata_bootstrap_failed",
                stage="autodata_bootstrap",
                retryable=True,
                public_summary="AutoData workspace bootstrap failed",
            )
            current = json.loads(marker_path.read_text(encoding="utf-8"))
            if (
                not isinstance(current, dict)
                or current.get("approved") is not True
                or current.get("journaled") is not True
                or any(
                    current.get(key) != value
                    for key, value in zip(
                        ("run_id", "idea_name", "code_hash"), identity, strict=True
                    )
                )
            ):
                raise RuntimeError(
                    "approved proposal changed during AutoData bootstrap retry"
                ) from error
            current["autodata_bootstrap"] = {
                "status": "failed",
                "error": failure["summary"],
                "failure": failure,
            }
            current["execution_ready"] = False
            _atomic_json_write(marker_path, current)
            raise FailureFeedbackError(failure) from error

        current = json.loads(marker_path.read_text(encoding="utf-8"))
        if (
            not isinstance(current, dict)
            or current.get("approved") is not True
            or current.get("journaled") is not True
            or any(
                current.get(key) != value
                for key, value in zip(
                    ("run_id", "idea_name", "code_hash"), identity, strict=True
                )
            )
        ):
            raise RuntimeError("approved proposal changed during AutoData bootstrap retry")
        current["autodata_bootstrap"] = {"status": "ready", **result}
        current["execution_ready"] = True
        _atomic_json_write(marker_path, current)
        print(
            "[AutoData bootstrap] workspace ready "
            f"workspace={result['workspace_id']} idempotent={result['idempotent']}"
        )

    def _recover_approved_proposal_receipt(self) -> None:
        """Repair only the marker bit backed by this chain's durable event."""

        from aar.research_loop.tools.server_api_tools import (
            _proposal_marker_path,
            ensure_proposal_journal_receipt,
        )

        marker_path = _proposal_marker_path()
        if not marker_path.is_file():
            return
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if (
            not isinstance(marker, dict)
            or marker.get("approved") is not True
            or marker.get("journaled") is True
        ):
            return
        marker_uid = marker.get("idea_uid")
        if not isinstance(marker_uid, str) or not marker_uid:
            raise FailureFeedbackError(
                build_failure_feedback(
                    RuntimeError("approved proposal marker has no idea UID"),
                    error_code="proposal_journal_failed",
                    stage="proposal_submission",
                    retryable=False,
                    public_summary="host-owned proposal journal update failed",
                )
            )
        recovered = ensure_proposal_journal_receipt(
            marker_path,
            team_dir=os.getenv("TEAM_DIR", ""),
            chain_id=self.idea_name,
            idea_uid=marker_uid,
            allow_backfill=False,
            mark_journaled=True,
        )
        if not recovered:
            raise FailureFeedbackError(
                build_failure_feedback(
                    RuntimeError("durable proposal journal event is missing"),
                    error_code="proposal_journal_failed",
                    stage="proposal_submission",
                    retryable=False,
                    public_summary="host-owned proposal journal update failed",
                )
            )

    async def run(self) -> Dict[str, Any]:
        """Run the autonomous agent loop."""
        mode_str = "local" if self.local_mode else "server"
        print(f"\n{'='*60}")
        print(f"Autonomous Agent Loop ({mode_str} mode)")
        print(f"  Run ID: {self.run_id}")
        print(f"  Idea: {self.idea_name} ({self.idea_uid})")
        backend = getattr(self, "backend", "claude")
        model = getattr(self, "model", "claude-opus-4-8")
        print(f"  Backend: {backend}")
        print(f"  Model: {model or 'Kimi configured default'}")
        print(f"  Max Runtime: {self.max_runtime_seconds/3600:.1f}h")
        print(f"  Max Iterations: {self.max_iterations if self.max_iterations is not None else 'unbounded'}")
        print(f"{'='*60}\n")

        # Initial findings sync (disabled in local mode)
        if self.findings_sync:
            try:
                count = self.findings_sync.sync_once()
                print(f"[Loop] Fetched {count} finding(s) from server")
            except Exception:
                print("[Loop] Warning: initial findings fetch failed")

            try:
                self.findings_sync.start()
            except Exception:
                print("[Loop] Warning: could not start findings sync")

        stop_reason = None
        successful_sessions = 0
        failed_sessions = 0
        last_failure: dict[str, Any] | None = None
        self._next_session_failure = None
        self._next_resume_run_id = None
        target_successful_pairs = int(
            os.getenv("AAR_TARGET_SUCCESSFUL_ITERATIONS", "0") or "0"
        )

        while True:
            if self.max_iterations is not None and self.session_count >= self.max_iterations:
                print(f"\n[Loop] Stopping: reached max iterations ({self.max_iterations})")
                stop_reason = "max_iterations"
                break
            stop_reason = self.stop_checker.check()
            if stop_reason:
                print(f"\n[Loop] Stopping: {stop_reason.value}")
                break

            if getattr(self, "backend", "claude") == "kimi":
                probe = self._create_agent(f"incident-check-{self.session_count}")
                incident = probe.active_orchestration_incident()
                if incident is not None:
                    nested = safe_failure_feedback_view(incident.get("failure"))
                    if nested is None:
                        nested = build_failure_feedback(
                            RuntimeError("shared orchestration incident"),
                            error_code="orchestration_incident",
                            stage="research_session",
                            public_summary="shared orchestration incident",
                        )
                    self._record_chain_memory_failure(nested)
                    code = (
                        nested["error_code"]
                    )
                    print(
                        "\n[Loop] Paused by shared orchestration incident: "
                        f"{code}"
                    )
                    stop_reason = "orchestration_incident"
                    break

            try:
                with phase(
                    "research.session",
                    metadata={
                        "session_index": self.session_count,
                        "idea_name": self.idea_name,
                    },
                ):
                    await self._run_session()
                self._reconcile_chain_memory()
                self.stop_checker.record_success()
                self._next_session_failure = None
                self._next_resume_run_id = None
                successful_sessions += 1
                if not self.local_mode:
                    await self._sync_to_s3()
                completed_pairs = self._successful_score_result_pairs()
                if target_successful_pairs and completed_pairs >= target_successful_pairs:
                    print(
                        f"\n[Loop] Stopping: reached {completed_pairs} atomic "
                        "score/result pairs"
                    )
                    stop_reason = "successful_iterations"
                    break

            except KeyboardInterrupt:
                print("\n[Loop] Interrupted")
                stop_reason = StopReason.USER_INTERRUPT
                break

            except OrchestrationIncident as error:
                failure = error.failure
                if not isinstance(failure, dict):
                    failure = build_failure_feedback(
                        error,
                        error_code="orchestration_incident",
                        stage="research_session",
                        public_summary="shared orchestration incident",
                    )
                last_failure = failure
                self._record_chain_memory_failure(last_failure)
                print(
                    "\n[Loop] Paused by orchestration incident: "
                    + str(failure["error_code"])
                )
                self.stop_checker.record_error()
                failed_sessions += 1
                stop_reason = "orchestration_incident"
                break

            except FailureFeedbackError as error:
                safe_failure = safe_failure_feedback_view(error.feedback)
                if safe_failure is None:
                    last_failure = build_failure_feedback(
                        error,
                        error_code="invalid_failure_feedback",
                        stage="research_session",
                        retryable=False,
                        public_summary="research session returned invalid failure feedback",
                    )
                else:
                    # Only the schema-validated, allowlisted view may influence
                    # retry policy or cross the research-session boundary.
                    last_failure = safe_failure
                self._record_chain_memory_failure(last_failure)
                print(
                    "\n[Loop] Session failure: "
                    + str(last_failure["error_code"])
                )
                self.stop_checker.record_error()
                failed_sessions += 1
                disposition = last_failure.get("disposition")
                if (
                    disposition == "halt"
                    and safe_failure is not None
                    and safe_failure.get("stage") in {"training", "evaluation"}
                    and isinstance(safe_failure.get("run_id"), str)
                ):
                    # Backward-compatible candidate evidence: the failed operation
                    # is terminal, but the research chain should author a new method.
                    disposition = "advance_session"
                if disposition == "advance_session":
                    self._next_session_failure = last_failure
                    run_id = last_failure.get("run_id")
                    if isinstance(run_id, str):
                        self._next_resume_run_id = run_id
                    print(
                        "[Loop] Advancing to a fresh research session from "
                        "durable lifecycle state"
                    )
                elif disposition == "retry_operation":
                    backoff = (
                        OVERLOADED_WAIT_SECONDS
                        if last_failure.get("error_code") == "kimi_model_overloaded"
                        else 30
                    )
                    await asyncio.sleep(backoff)
                else:
                    stop_reason = "permanent_session_failure"
                    break

            except Exception as e:
                last_failure = build_failure_feedback(
                    e,
                    error_code="research_session_failed",
                    stage="research_session",
                    retryable=False,
                    public_summary="research session failed",
                )
                self._record_chain_memory_failure(last_failure)
                print("\n[Loop] Session failure: research_session_failed")
                self.stop_checker.record_error()
                failed_sessions += 1
                stop_reason = "permanent_session_failure"
                break
            finally:
                # `--max-iterations` caps sessions that BEGIN, not only sessions
                # that finish successfully.  A failed first session may already
                # have trained/submitted a method; silently opening a retry
                # session would violate the one-iteration smoke contract and can
                # produce a second method/submission.
                self.session_count += 1

        if self.findings_sync:
            try:
                self.findings_sync.stop()
            except Exception:
                pass

        if not self.local_mode:
            await self._sync_to_s3()

        result = {
            "run_id": self.run_id,
            "idea_uid": self.idea_uid,
            "idea_name": self.idea_name,
            "sessions": self.session_count,
            "duration_seconds": self.stop_checker.elapsed_time,
            "stop_reason": (
                stop_reason.value if isinstance(stop_reason, StopReason)
                else stop_reason or "unknown"
            ),
            "successful_sessions": successful_sessions,
            "failed_sessions": failed_sessions,
            "successful_score_result_pairs": self._successful_score_result_pairs(),
        }
        if last_failure is not None:
            result["last_failure"] = last_failure

        summary_dir = getattr(self, "logs_dir", None)
        if summary_dir is not None:
            summary_path = Path(summary_dir) / "run_summary.json"
            summary_tmp = summary_path.with_suffix(".json.tmp")
            summary_tmp.write_text(json.dumps(result, indent=2) + "\n")
            os.replace(summary_tmp, summary_path)

        print(f"\n{'='*60}")
        print(f"Done: {result['sessions']} sessions, "
              f"{result['duration_seconds']/3600:.1f}h, "
              f"reason={result['stop_reason']}")
        print(f"{'='*60}\n")

        return result

    def _reconcile_chain_memory(self) -> None:
        journal = getattr(self, "chain_memory", None)
        if journal is not None:
            try:
                journal.reconcile()
            except Exception as error:
                raise FailureFeedbackError(
                    build_failure_feedback(
                        error,
                        error_code="chain_memory_integrity_failed",
                        stage="research_session",
                        retryable=False,
                        public_summary="host-owned chain memory integrity check failed",
                    )
                ) from error

    def _record_chain_memory_failure(self, failure: object) -> None:
        """Persist only the schema-validated public failure view.

        Never mask the original controller disposition if auxiliary journaling
        itself fails, and never print the raw journal exception.
        """

        journal = getattr(self, "chain_memory", None)
        if journal is None:
            return
        try:
            journal.record_failure(
                failure,
                session_id=getattr(self, "_last_session_id", None)
                or os.getenv("AAR_CURRENT_SESSION_ID")
                or f"{self.run_id}-session-{self.session_count:03d}",
            )
            journal.reconcile()
        except Exception:  # noqa: BLE001 - preserve the original safe failure
            print("[Loop] Warning: host-owned chain-memory failure record was not updated")

    def _successful_score_result_pairs(self) -> int:
        """Count durable score/result intersections, never session completions."""
        configured = os.getenv("TEAM_DIR")
        fallback_logs = getattr(self, "logs_dir", Path.cwd() / "logs")
        team_dir = Path(configured) if configured else Path(fallback_logs).parent
        score_ids: set[str] = set()
        for path in (team_dir / "scores").glob("*.json"):
            if path.name.endswith(".failed.json"):
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and isinstance(
                value.get("headline_pct"), (int, float)
            ):
                score_ids.add(path.stem)
        result_ids: set[str] = set()
        for path in (team_dir / "forum").glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(value, dict)
                and value.get("finding_type") == "result"
                and isinstance(value.get("run_id"), str)
            ):
                result_ids.add(value["run_id"])
        return len(score_ids & result_ids)

    async def _run_session(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Chain identity in the session id: parallel chains that start in the SAME
        # second otherwise collide on ONE session_<ts>.log (observed: 4 chains ->
        # one transcript, so the dashboard showed identical trajectories for all).
        _tag = re.sub(r"[^A-Za-z0-9]+", "_", self.idea_name or "chain").strip("_") or "chain"
        session_id = f"session_{self.session_count:03d}_{_tag}_{timestamp}"
        self._last_session_id = session_id
        log_file = self.logs_dir / f"{session_id}.log"
        os.environ["AAR_CURRENT_SESSION_ID"] = session_id

        print(f"\n[Session {self.session_count}] {session_id}")

        # Reconcile before either backend starts.  This repairs the narrow crash
        # windows where a lifecycle artifact became durable after the previous
        # process's last journal write.  Then repair the proposal marker receipt
        # before Kimi or Claude can inspect it directly.
        self._reconcile_chain_memory()
        self._recover_approved_proposal_receipt()
        self._ensure_approved_autodata_workspace()
        prompt = self._get_prompt()
        journal = getattr(self, "chain_memory", None)
        if journal is not None:
            prompt += (
                "\n\nHOST-OWNED MEMORY FOR THIS CHAIN (authoritative, read-only; "
                "do not edit it):\n\n" + journal.prompt_snapshot()
            )
        next_failure = getattr(self, "_next_session_failure", None)
        if isinstance(next_failure, dict):
            prompt += (
                "\n\nAUTOMATIC SAFE HANDOFF FROM THE PREVIOUS RESEARCH SESSION:\n"
                + json.dumps(next_failure, sort_keys=True)
                + "\nTreat `guidance` as the required correction and `disposition` "
                "as the controller decision. Continue from durable artifacts. Do not "
                "repeat an unchanged contract error, proposal, training submission, "
                "or run ID."
            )

        with open(log_file, "w") as log_f:
            log_f.write(f"# Session {session_id}\n# Started: {datetime.now().isoformat()}\n\n")

            def message_callback(message):
                ts = datetime.now().strftime("%H:%M:%S")
                log_f.write(f"\n[{ts}] {type(message).__name__}\n")
                if hasattr(message, "content"):
                    for content in message.content:
                        if hasattr(content, "thinking"):   # ThinkingBlock — RAW extended reasoning
                            log_f.write(f"[THINKING]\n{content.thinking}\n")
                        elif hasattr(content, "text"):
                            log_f.write(f"{content.text}\n")
                        elif hasattr(content, "name"):
                            log_f.write(f"Tool: {content.name}\n")
                            if hasattr(content, "input"):
                                input_str = json.dumps(content.input, indent=2)
                                if len(input_str) > 1000:
                                    input_str = input_str[:1000] + "... [truncated]"
                                log_f.write(f"Input: {input_str}\n")
                log_f.flush()

            try:
                agent = self._create_agent(session_id, message_callback=message_callback)
                resume_run_id = getattr(self, "_next_resume_run_id", None)
                prior_resume = os.environ.get("AAR_RESUME_APPROVED_PROPOSAL")
                prior_expected = os.environ.get("AAR_RESUME_EXPECTED_RUN_ID")
                if isinstance(resume_run_id, str):
                    os.environ["AAR_RESUME_APPROVED_PROPOSAL"] = "1"
                    os.environ["AAR_RESUME_EXPECTED_RUN_ID"] = resume_run_id
                try:
                    result = await agent.execute(task=prompt)
                finally:
                    if isinstance(resume_run_id, str):
                        if prior_resume is None:
                            os.environ.pop("AAR_RESUME_APPROVED_PROPOSAL", None)
                        if prior_expected is None:
                            os.environ.pop("AAR_RESUME_EXPECTED_RUN_ID", None)

                log_f.write(f"\n# Result: success={result.success}, "
                           f"duration={result.duration:.1f}s, "
                           f"tools={result.iteration_count}\n")
                if result.error:
                    failure = getattr(result, "failure", None)
                    code = (
                        failure.get("error_code")
                        if isinstance(failure, dict)
                        else "agent_backend_failed"
                    )
                    log_f.write(f"# Error code: {code}\n")

                if not result.success:
                    failure = getattr(result, "failure", None)
                    if isinstance(failure, dict):
                        raise FailureFeedbackError(failure)
                    feedback = build_failure_feedback(
                        RuntimeError(result.error or "agent failed"),
                        error_code="agent_backend_failed",
                        stage="research_session",
                        retryable=False,
                        public_summary="research agent backend failed",
                    )
                    raise FailureFeedbackError(feedback)

            except Exception as e:
                if isinstance(e, FailureFeedbackError):
                    log_f.write(
                        "\n# ERROR_CODE: "
                        + str(e.feedback.get("error_code"))
                        + "\n"
                    )
                    raise
                feedback = build_failure_feedback(
                    e,
                    error_code="research_session_failed",
                    stage="research_session",
                    public_summary="research session failed",
                )
                log_f.write("\n# ERROR_CODE: research_session_failed\n")
                raise FailureFeedbackError(feedback) from e
            finally:
                log_f.write(f"\n# Ended: {datetime.now().isoformat()}\n")
                os.environ.pop("AAR_CURRENT_SESSION_ID", None)

        print(f"[Session {self.session_count}] Completed")

    async def _sync_to_s3(self):
        try:
            from aar.infrastructure.s3_utils import upload_file_to_s3
        except ImportError:
            return

        try:
            if self.findings_path.exists():
                upload_file_to_s3(
                    file_path=self.findings_path,
                    s3_key=f"{self.s3_prefix}findings.json",
                    bucket_name=self.s3_bucket,
                    content_type="application/json",
                )
            for log_file in self.logs_dir.glob("session_*.log"):
                upload_file_to_s3(
                    file_path=log_file,
                    s3_key=f"{self.s3_prefix}logs/{log_file.name}",
                    bucket_name=self.s3_bucket,
                    content_type="text/plain",
                )
        except Exception:
            print("[Sync] Failed")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main():
    import sys
    idea_uid = os.getenv("IDEA_UID") or (sys.argv[1] if len(sys.argv) > 1 else None)
    idea_name = os.getenv("IDEA_NAME", "unknown")
    local_mode = os.getenv("LOCAL_MODE", "false").lower() in ("1", "true", "yes")

    if not idea_uid:
        print("Usage: python -m aar.research_loop.agent <idea_uid>")
        print("   Or: IDEA_UID=... python -m aar.research_loop.agent")
        sys.exit(1)

    loop = AutonomousAgentLoop(idea_uid=idea_uid, idea_name=idea_name, local_mode=local_mode)
    await loop.run()


if __name__ == "__main__":
    asyncio.run(main())
