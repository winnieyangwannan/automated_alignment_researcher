#!/usr/bin/env python3
"""Require a complete Kimi -> AAR MCP tool -> Kimi round trip."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from aar.research_loop.kimi_agent import KimiAgent


async def verify(workspace: Path) -> dict[str, object]:
    deployment = os.environ.get("AAR_KIMI_SERVE_DEPLOYMENT", "").strip()
    expected_model = os.environ.get("AAR_KIMI_EXPECTED_MODEL", "").strip()
    if not deployment or not expected_model:
        raise RuntimeError(
            "AAR_KIMI_SERVE_DEPLOYMENT and AAR_KIMI_EXPECTED_MODEL are required"
        )
    turn_timeout = int(os.environ.get("AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS", "180"))
    if turn_timeout < 30 or turn_timeout > 600:
        raise RuntimeError("AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS must be 30..600")
    max_output_tokens = int(
        os.environ.get("AAR_KIMI_PREFLIGHT_MAX_OUTPUT_TOKENS", "1024")
    )
    if max_output_tokens < 128 or max_output_tokens > 4096:
        raise RuntimeError(
            "AAR_KIMI_PREFLIGHT_MAX_OUTPUT_TOKENS must be 128..4096"
        )
    # A health probe must not inherit the research session's 65,536-token
    # allowance. Kimi can otherwise generate until the wall-clock timeout
    # without reaching its first tool call, consuming capacity while proving
    # nothing. This override is local to the verifier process.
    os.environ["KIMI_MODEL_MAX_OUTPUT_SIZE"] = str(max_output_tokens)
    os.environ["KIMI_MODEL_MAX_COMPLETION_TOKENS"] = str(max_output_tokens)
    try:
        result = await asyncio.wait_for(
            KimiAgent(
                "run10-preflight",
                workspace,
                model=None,
                cli_path=os.environ.get("KIMI_CLI_PATH"),
                include_prior_work=True,
                system_prompt=(
                    "You are a noninteractive endpoint verifier. Follow the user's "
                    "exact tool sequence and do not create or manage a separate goal."
                ),
                disallowed_tools=[
                    "CreateGoal",
                    "UpdateGoal",
                    "SetGoalBudget",
                    "TodoList",
                    "WaitFor",
                    "Agent",
                    "AgentSwarm",
                ],
                completion_tool="get_literature",
                max_continuations=2,
                auto_approve=True,
                force_checkpoint_tools=True,
                turn_timeout_seconds=turn_timeout,
            ).execute(
                "Call the get_literature MCP tool exactly once with query set to "
                "__aar_endpoint_preflight_no_match__. After receiving that tool "
                "result, reply with exactly KIMI_MCP_CANARY_OK."
            ),
            timeout=turn_timeout + 10,
        )
    except TimeoutError as error:
        raise RuntimeError(
            f"Kimi MCP round trip exceeded {turn_timeout} seconds"
        ) from error
    tools = [str(item.get("tool", "")) for item in result.output.get("tool_uses", [])]
    texts = [str(item) for item in result.output.get("text_outputs", [])]
    literature_positions = [
        index
        for index, name in enumerate(tools)
        if name == "get_literature" or name.endswith("get_literature")
    ]
    tool_ok = len(literature_positions) == 1
    response_ok = any(
        text.strip().endswith("KIMI_MCP_CANARY_OK") for text in texts
    )
    if not result.success or not tool_ok or not response_ok:
        stderr_tail = str(result.output.get("stderr", ""))[-2000:]
        raise RuntimeError(
            f"Kimi MCP round trip failed: success={result.success}, tools={tools}, "
            f"response_ok={response_ok}, error={result.error}, stderr={stderr_tail}"
        )

    try:
        forced_result = await asyncio.wait_for(
            KimiAgent(
                "run10-forced-tool-preflight",
                workspace,
                model=None,
                cli_path=os.environ.get("KIMI_CLI_PATH"),
                include_prior_work=False,
                system_prompt=(
                    "You are a noninteractive endpoint verifier. Follow the user's "
                    "exact two-turn instruction and do not create or manage a separate "
                    "goal."
                ),
                disallowed_tools=[
                    "CreateGoal",
                    "UpdateGoal",
                    "SetGoalBudget",
                    "TodoList",
                    "WaitFor",
                    "Agent",
                    "AgentSwarm",
                ],
                completion_tool="Bash",
                max_continuations=2,
                auto_approve=True,
                force_checkpoint_tools=True,
                turn_timeout_seconds=turn_timeout,
            ).execute(
                "In this first turn, do not call any tool; reply exactly "
                "KIMI_FORCE_READY. On the later turn that requires Bash, call it with "
                "command `printf KIMI_FORCE_OK`."
            ),
            timeout=turn_timeout + 10,
        )
    except TimeoutError as error:
        raise RuntimeError(
            f"Kimi named-tool checkpoint exceeded {turn_timeout} seconds"
        ) from error
    forced_uses = [
        item
        for item in forced_result.output.get("tool_uses", [])
        if str(item.get("tool", "")).rsplit("__", 1)[-1] == "Bash"
    ]
    forced_commands = [
        str((item.get("input") or {}).get("command", ""))
        for item in forced_uses
    ]
    forced_ok = (
        forced_result.success
        and forced_result.output.get("continuations", 0) >= 1
        and bool(forced_commands)
        and all(command == "printf KIMI_FORCE_OK" for command in forced_commands)
    )
    if not forced_ok:
        raise RuntimeError(
            "Kimi named tool-choice checkpoint failed: "
            f"success={forced_result.success}, continuations="
            f"{forced_result.output.get('continuations')}, tools={forced_uses}, "
            f"error={forced_result.error}"
        )
    return {
        "status": "passed",
        "model": expected_model,
        "deployment": deployment,
        "bash_tool_roundtrip": True,
        "mcp_tool_roundtrip": True,
        "sequential_mcp_tool_roundtrips": 1,
        "named_tool_choice_checkpoint": True,
        "preflight_max_output_tokens": max_output_tokens,
        "tools": [*tools, "Bash"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = asyncio.run(verify(args.workspace.resolve()))
    args.output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print("Kimi endpoint and AAR MCP round trip passed")


if __name__ == "__main__":
    main()
