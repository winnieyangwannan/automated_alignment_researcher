#!/usr/bin/env python3
"""One-call smoke test for Meta Claude plus the restricted arXiv helper.

This is intentionally not a librarian run: it creates one short Agent SDK
session and asks for exactly one search call.  Run it in an environment with
claude-agent-sdk 0.2.157 and Meta's authenticated ``/usr/local/bin/claude``.
"""

from __future__ import annotations

import argparse
import asyncio
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)


REQUIRED_SDK_VERSION = "0.2.157"
CLAUDE_CLI_PATH = "/usr/local/bin/claude"


async def smoke(query: str) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[1]
    helper = (repo / "scripts" / "aar-paper-search").resolve()
    if not helper.is_file() or not os.access(helper, os.X_OK):
        raise RuntimeError(f"paper helper is not executable: {helper}")
    if version("claude-agent-sdk") != REQUIRED_SDK_VERSION:
        raise RuntimeError(
            f"smoke requires claude-agent-sdk {REQUIRED_SDK_VERSION}; "
            f"found {version('claude-agent-sdk')}"
        )
    if not Path(CLAUDE_CLI_PATH).is_file() or not os.access(CLAUDE_CLI_PATH, os.X_OK):
        raise RuntimeError(f"Meta Claude CLI is not executable: {CLAUDE_CLI_PATH}")

    os.environ["META_CLAUDE_SECURE_INTERNET_MODE"] = "1"
    for secret_name in (
        "ANTHROPIC_API_KEY",
        "MODEL_API_KEY",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
    ):
        os.environ.pop(secret_name, None)
    allowed_rule = f"Bash({helper} search *)"
    tool_uses: list[dict[str, Any]] = []
    text_parts: list[str] = []

    with tempfile.TemporaryDirectory(prefix="aar-paper-smoke-") as workspace:
        options = ClaudeAgentOptions(
            allowed_tools=[allowed_rule],
            permission_mode="dontAsk",
            cli_path=CLAUDE_CLI_PATH,
            cwd=workspace,
            model="claude-sonnet-4-6",
            setting_sources=[],
            max_turns=3,
        )
        prompt = (
            "Use the approved aar-paper-search helper exactly once to search arXiv for "
            f"{query!r}, with --limit 1. Do not use any other tool. Then report the first "
            "paper's exact title and arXiv ID."
        )
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tool_uses.append({"name": block.name, "input": block.input})
                        elif isinstance(block, TextBlock):
                            text_parts.append(block.text)
                if isinstance(message, ResultMessage):
                    if message.is_error:
                        raise RuntimeError(f"Claude smoke returned an error: {message.result}")
                    break

    if len(tool_uses) != 1 or tool_uses[0]["name"] != "Bash":
        raise RuntimeError(f"expected one Bash helper call; observed {tool_uses!r}")
    command = str(tool_uses[0]["input"].get("command", ""))
    if not command.startswith(f"{helper} search "):
        raise RuntimeError(f"Claude invoked an unexpected command: {command!r}")
    answer = "\n".join(text_parts).strip()
    if not re.search(r"\b\d{4}\.\d{4,5}(?:v\d+)?\b", answer):
        raise RuntimeError(f"Claude answer did not contain a modern arXiv ID: {answer!r}")
    return {
        "ok": True,
        "sdk_version": REQUIRED_SDK_VERSION,
        "secure_internet_mode": True,
        "permission_mode": "dontAsk",
        "allowed_tools": [allowed_rule],
        "tool_uses": tool_uses,
        "answer": answer,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="sycophancy language models")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(smoke(args.query)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
