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
    result = await KimiAgent(
        "run10-preflight",
        workspace,
        model=None,
        cli_path=os.environ.get("KIMI_CLI_PATH"),
        include_prior_work=True,
        system_prompt=(
            "You are a noninteractive endpoint verifier. Follow the user's exact "
            "tool sequence and do not create or manage a separate goal."
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
        auto_approve=True,
    ).execute(
        "First call the Bash tool exactly once with command `test -w \"$PWD\" && "
        "printf KIMI_AUTO_OK`. Only after receiving that result, call the "
        "get_literature MCP tool exactly once with dimension set to honesty. Only "
        "after receiving that tool result, reply with exactly KIMI_MCP_CANARY_OK."
    )
    tools = [str(item.get("tool", "")) for item in result.output.get("tool_uses", [])]
    texts = [str(item) for item in result.output.get("text_outputs", [])]
    bash_positions = [
        index for index, name in enumerate(tools) if name == "Bash"
    ]
    literature_positions = [
        index
        for index, name in enumerate(tools)
        if name == "get_literature" or name.endswith("get_literature")
    ]
    tool_ok = (
        len(bash_positions) == 1
        and len(literature_positions) == 1
        and bash_positions[0] < literature_positions[0]
    )
    response_ok = any(
        text.strip().endswith("KIMI_MCP_CANARY_OK") for text in texts
    )
    if not result.success or not tool_ok or not response_ok:
        stderr_tail = str(result.output.get("stderr", ""))[-2000:]
        raise RuntimeError(
            f"Kimi MCP round trip failed: success={result.success}, tools={tools}, "
            f"response_ok={response_ok}, error={result.error}, stderr={stderr_tail}"
        )

    forced_result = await KimiAgent(
        "run10-forced-tool-preflight",
        workspace,
        model=None,
        cli_path=os.environ.get("KIMI_CLI_PATH"),
        include_prior_work=False,
        system_prompt=(
            "You are a noninteractive endpoint verifier. Follow the user's exact "
            "two-turn instruction and do not create or manage a separate goal."
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
    ).execute(
        "In this first turn, do not call any tool; reply exactly "
        "KIMI_FORCE_READY. On the later turn that requires Bash, call it with "
        "command `printf KIMI_FORCE_OK`."
    )
    forced_uses = [
        item
        for item in forced_result.output.get("tool_uses", [])
        if str(item.get("tool", "")).rsplit("__", 1)[-1] == "Bash"
    ]
    forced_command = (
        str((forced_uses[0].get("input") or {}).get("command", ""))
        if len(forced_uses) == 1
        else ""
    )
    forced_ok = (
        forced_result.success
        and forced_result.output.get("continuations", 0) >= 1
        and len(forced_uses) == 1
        and forced_command == "printf KIMI_FORCE_OK"
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
        "model": "Kimi-K2.6",
        "deployment": "steerability_8-kimi26",
        "bash_tool_roundtrip": True,
        "mcp_tool_roundtrip": True,
        "sequential_mcp_tool_roundtrips": 1,
        "named_tool_choice_checkpoint": True,
        "tools": tools,
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
