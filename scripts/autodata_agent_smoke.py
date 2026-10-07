#!/usr/bin/env python3
"""Run one live, bounded AAR agent session against the AutoData adapter.

This smoke intentionally does not train or evaluate a model.  It gives one real
``BaseAgent`` session only the AutoData MCP tools, asks that agent to create and
drive a pre-approved deterministic job, then verifies that the method fixture
loads the fetched rows through ``load_autodata_dataset``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any


AUTODATA_SPEC = {
    "schema": "aar.autodata.request/v1",
    "resource_profile": "run8-agent-smoke-v1",
    "safety_axis": "dishonest_sycophancy_concealing",
    "training_mechanism": "deterministic integration smoke only; no training",
    "training_view": "sft",
    "seed": 8,
    "goal": (
        "Exercise native workspace creation, meta-optimization, production, "
        "artifact fetch, and verified dataset loading without benchmark access."
    ),
}

REQUIRED_AGENT_TOOLS = {
    "mcp__autodata-tools__autodata_generate",
    "mcp__autodata-tools__autodata_step",
    "mcp__autodata-tools__autodata_fetch",
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _method_source() -> str:
    """Return a literal-spec method fixture whose only executable action is loading data."""
    return (
        "from aar.infrastructure.autodata import load_autodata_dataset\n\n"
        f"AUTODATA_SPEC = {AUTODATA_SPEC!r}\n\n"
        "def load_training_rows():\n"
        "    return load_autodata_dataset()\n"
    )


def _agent_prompt(run_id: str, idea_name: str) -> str:
    return f"""You are executing one bounded AutoData integration smoke for AAR.

Use only the AutoData MCP tools exposed in this session. Do not train or evaluate
a model, inspect benchmarks, use a shell, browse files, or create a second run.

The pre-approved identifiers are:
- run_id: {run_id}
- idea_name: {idea_name}

Perform this sequence without asking a human for approval:
1. Call autodata_generate exactly once with the identifiers above. This call must
   initiate the operator-pinned AutoData workspace/job.
2. Call autodata_step to start or advance its unattended native lifecycle.
3. Call autodata_status as needed until state is complete. If it is queued or
   running, continue polling; do not abandon the session early. If it fails,
   report the service error and stop.
4. Once complete, call autodata_fetch for the same run_id.
5. Confirm the fetch response reports success and finish with the exact text
   AUTODATA_AGENT_SMOKE_COMPLETE.

Never call training, evaluation, proposal, web, filesystem, or shell tools.
"""


def _read_json(url: str, timeout: int) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return value


def _configure_environment(
    *, root: Path, service_url: str, pipeline_sha: str, run_id: str
) -> None:
    profile_digest = hashlib.sha256(_canonical_json(AUTODATA_SPEC)).hexdigest()
    values = {
        "TEAM_DIR": str(root / "team"),
        "SCORES_DIR": str(root / "team" / "scores"),
        "AAR_IDEAS_DIR": str(root / "team" / "methods"),
        "RUN_ID": run_id,
        "AAR_CURRENT_RUN_ID": run_id,
        "AAR_AUTODATA": "1",
        "AAR_AUTODATA_REQUIRED": "1",
        "AAR_AUTODATA_URL": service_url.rstrip("/"),
        "AAR_AUTODATA_SHA": pipeline_sha,
        "AAR_AUTODATA_RESOURCE_PROFILE": AUTODATA_SPEC["resource_profile"],
        "AAR_AUTODATA_RESOURCE_PROFILE_SHA256": profile_digest,
        "AAR_AUTODATA_BUDGET_SCOPE_ID": "run8-agent-smoke-campaign",
        "AAR_AUTODATA_MAX_COST_USD": "1.00",
        "AAR_AUTODATA_REQUIRED_RETAINED_ROWS": "10",
        "AAR_AUTODATA_HTTP_TIMEOUT": "120",
    }
    os.environ.update(values)


def _prepare_approved_fixture(root: Path, run_id: str, idea_name: str) -> Path:
    """Create the deterministic method and immutable approval binding for this smoke."""
    from aar import config
    from aar.research_loop.tools.autodata_tools import _spec_digest
    from aar.research_loop.tools.server_api_tools import _method_code

    method_dir = Path(config.IDEAS_DIR) / idea_name
    method_dir.mkdir(parents=True, exist_ok=False)
    method_path = method_dir / "run.py"
    method_path.write_text(_method_source())
    code, code_hash = _method_code(idea_name)
    if not code or not code_hash:
        raise RuntimeError("could not hash deterministic smoke method")
    proposal = Path(os.environ["SCORES_DIR"]) / ".proposals" / "runs" / f"{run_id}.json"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "idea_name": idea_name,
                "proposal_ts": time.time(),
                "code_hash": code_hash,
                "autodata_spec_sha256": _spec_digest(AUTODATA_SPEC),
                "autodata_resource_profile": AUTODATA_SPEC["resource_profile"],
                "autodata_budget_scope_id": os.environ["AAR_AUTODATA_BUDGET_SCOPE_ID"],
                "paper": {
                    "title": "Bounded AutoData agent integration smoke",
                    "data": "Operator-pinned deterministic toy recipe; no benchmark data.",
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return method_path


def _load_through_method(method_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from aar.infrastructure.autodata import verify_autodata_consumption

    spec = importlib.util.spec_from_file_location("aar_autodata_agent_smoke_method", method_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import method fixture {method_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.load_training_rows()
    receipt = verify_autodata_consumption()
    if receipt["row_count"] != len(rows):
        raise RuntimeError("consumption receipt does not match loaded rows")
    return rows, receipt


async def _run_agent(
    *, root: Path, prompt: str, idea_name: str, model: str
) -> tuple[dict[str, Any], list[str]]:
    from claude_agent_sdk import AssistantMessage, ToolUseBlock

    from aar.research_loop.agent import AutonomousAgentLoop, BaseAgent
    from aar.research_loop.tools.autodata_tools import create_autodata_tools_server

    observed_tools: list[str] = []

    class AutoDataSmokeLoop(AutonomousAgentLoop):
        def _get_prompt(self) -> str:
            return prompt

        def _create_agent(self, session_id: str, message_callback=None) -> BaseAgent:
            def observe(message: Any) -> None:
                if message_callback is not None:
                    message_callback(message)
                if isinstance(message, AssistantMessage):
                    observed_tools.extend(
                        content.name
                        for content in message.content
                        if isinstance(content, ToolUseBlock)
                    )

            return BaseAgent(
                name=f"autodata-smoke-{session_id}",
                allowed_tools=sorted(REQUIRED_AGENT_TOOLS | {
                    "mcp__autodata-tools__autodata_status",
                }),
                workspace=Path.cwd(),
                mcp_servers={"autodata-tools": create_autodata_tools_server()},
                model=model,
                cli_path=os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude"),
                message_callback=observe,
                permission_mode="bypassPermissions",
                system_prompt=(
                    "Execute only the bounded AutoData smoke procedure in the user prompt. "
                    "Never train, evaluate, inspect benchmarks, or use non-AutoData tools."
                ),
                tools=[],
                setting_sources=[],
                strict_mcp_config=True,
            )

    loop = AutoDataSmokeLoop(
        idea_uid="run8-autodata-agent-smoke",
        idea_name=idea_name,
        workspace=Path.cwd(),
        logs_dir=root / "logs",
        max_runtime_seconds=900,
        max_iterations=1,
        model=model,
        local_mode=True,
    )
    return await loop.run(), observed_tools


async def _main(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    service_url = args.service_url.rstrip("/")
    health = _read_json(f"{service_url}/health", args.health_timeout)
    if health.get("status") != "ok" or health.get("pipeline_sha") != args.pipeline_sha:
        raise RuntimeError(f"AutoData adapter health/pipeline mismatch: {health}")

    run_id = args.run_id or f"autodata-agent-smoke-{uuid.uuid4().hex[:12]}"
    idea_name = "autodata_agent_smoke_method"
    _configure_environment(
        root=output_root,
        service_url=service_url,
        pipeline_sha=args.pipeline_sha,
        run_id=run_id,
    )
    method_path = _prepare_approved_fixture(output_root, run_id, idea_name)
    prompt = _agent_prompt(run_id, idea_name)
    (output_root / "agent_prompt.md").write_text(prompt)

    loop_result, observed_tools = await _run_agent(
        root=output_root,
        prompt=prompt,
        idea_name=idea_name,
        model=args.model,
    )
    missing = sorted(REQUIRED_AGENT_TOOLS - set(observed_tools))
    if loop_result.get("successful_sessions") != 1 or missing:
        raise RuntimeError(
            f"live AAR agent did not complete the required tool path; missing={missing}, "
            f"loop={loop_result}"
        )
    status = _read_json(f"{service_url}/v1/runs/{run_id}", args.health_timeout)
    if status.get("state") != "complete":
        raise RuntimeError(f"AutoData service did not complete: {status}")
    rows, receipt = _load_through_method(method_path)
    artifact_dir = output_root / "team" / "autodata" / run_id
    manifest = json.loads((artifact_dir / "autodata_manifest.json").read_text())
    expected_modes = ["meta_optimize", "production"]
    if manifest.get("modes_completed_in_order") != expected_modes:
        raise RuntimeError(
            "AutoData did not complete meta-optimization before production: "
            f"{manifest.get('modes_completed_in_order')}"
        )
    if manifest.get("workspace_id") != status.get("workspace_id"):
        raise RuntimeError("fetched manifest and service status disagree on workspace_id")
    report = {
        "schema": "aar.autodata.agent-smoke/v1",
        "run_id": run_id,
        "pipeline_sha": args.pipeline_sha,
        "agent_model": args.model,
        "loop": loop_result,
        "observed_tools": observed_tools,
        "service_status": status,
        "modes_completed_in_order": manifest["modes_completed_in_order"],
        "workspace_id": manifest["workspace_id"],
        "meta_optimize_execution_id": manifest["meta_optimize_execution_id"],
        "production_execution_id": manifest["production_execution_id"],
        "loaded_row_count": len(rows),
        "dataset_sha256": receipt["dataset_sha256"],
        "consumption_receipt": str(artifact_dir / "autodata_consumption.json"),
        "training_or_evaluation_performed": False,
    }
    report_path = output_root / "agent_smoke_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"AUTODATA_AGENT_SMOKE_PASS report={report_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-url", default="http://127.0.0.1:8792")
    parser.add_argument("--pipeline-sha", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--model", default=os.getenv("AAR_AGENT_MODEL", "claude-opus-4-8"))
    parser.add_argument("--health-timeout", type=int, default=10)
    args = parser.parse_args()
    if shutil.which("claude") is None:
        raise SystemExit("claude CLI is required for the live AAR agent smoke")
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
