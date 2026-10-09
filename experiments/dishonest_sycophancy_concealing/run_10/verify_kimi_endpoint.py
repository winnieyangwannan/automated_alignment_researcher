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
        "get_leaderboard MCP tool exactly once with its valid empty input. "
        "Only after receiving that result, call the get_literature MCP tool exactly "
        "once with dimension set to honesty. Only after receiving the second tool "
        "result, reply with exactly KIMI_MCP_CANARY_OK."
    )
    tools = [str(item.get("tool", "")) for item in result.output.get("tool_uses", [])]
    texts = [str(item) for item in result.output.get("text_outputs", [])]
    bash_positions = [
        index for index, name in enumerate(tools) if name == "Bash"
    ]
    leaderboard_positions = [
        index
        for index, name in enumerate(tools)
        if name == "get_leaderboard" or name.endswith("get_leaderboard")
    ]
    literature_positions = [
        index
        for index, name in enumerate(tools)
        if name == "get_literature" or name.endswith("get_literature")
    ]
    tool_ok = (
        len(bash_positions) == 1
        and len(leaderboard_positions) == 1
        and len(literature_positions) == 1
        and bash_positions[0] < leaderboard_positions[0] < literature_positions[0]
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
    return {
        "status": "passed",
        "model": "Kimi-K2.6",
        "deployment": "steerability_8-kimi26",
        "bash_tool_roundtrip": True,
        "mcp_tool_roundtrip": True,
        "sequential_mcp_tool_roundtrips": 2,
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
