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
    ).execute(
        "Call the get_leaderboard MCP tool exactly once with its valid empty input. "
        "After receiving the tool result, reply with exactly KIMI_MCP_CANARY_OK."
    )
    tools = [str(item.get("tool", "")) for item in result.output.get("tool_uses", [])]
    texts = [str(item) for item in result.output.get("text_outputs", [])]
    tool_ok = any(name == "get_leaderboard" or name.endswith("get_leaderboard") for name in tools)
    response_ok = any("KIMI_MCP_CANARY_OK" in text for text in texts)
    if not result.success or not tool_ok or not response_ok:
        raise RuntimeError(
            f"Kimi MCP round trip failed: success={result.success}, tools={tools}, "
            f"response_ok={response_ok}, error={result.error}"
        )
    return {
        "status": "passed",
        "model": "Kimi-K2.6",
        "deployment": "steerability_8-kimi26",
        "mcp_tool_roundtrip": True,
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
