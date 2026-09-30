#!/usr/bin/env python3
"""Exercise the production AAR's CPU boundary, secure web, and literature MCP tools."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, ToolUseBlock

from aar.research_loop.tools.server_api_tools import create_literature_tools_server


async def run() -> dict:
    repo = Path(os.environ["AAR_REPO"])
    helper = (repo / "scripts" / "aar-paper-search").resolve()
    gpu_check = (repo / "replication" / "check_no_gpu.sh").resolve()
    for name in (
        "ANTHROPIC_API_KEY", "MODEL_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN",
        "OAI_API", "OPENAI_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    ):
        os.environ.pop(name, None)
    os.environ["META_CLAUDE_SECURE_INTERNET_MODE"] = "1"

    with tempfile.TemporaryDirectory(prefix="aar-v0-web-") as tmp:
        root = Path(tmp)
        os.environ["LIT_AXIS_DIR"] = str(root / "axis_literature")
        os.environ["LIT_FORUM_DIR"] = str(root / "team_literature")
        (root / "axis_literature").mkdir()
        (root / "team_literature").mkdir()
        tools = []
        options = ClaudeAgentOptions(
            allowed_tools=[
                f"Bash({helper} *)",
                f"Bash({gpu_check})",
                "mcp__server-api-tools__get_literature",
                "mcp__server-api-tools__share_literature",
            ],
            permission_mode="dontAsk",
            cli_path=os.environ.get("CLAUDE_CLI_PATH", "/usr/local/bin/claude"),
            cwd=str(root),
            model="claude-sonnet-4-6",
            mcp_servers={"server-api-tools": create_literature_tools_server()},
            tools=["Bash"],
            setting_sources=[],
            strict_mcp_config=True,
            thinking={"type": "adaptive", "display": "summarized"},
            effort="max",
            max_turns=10,
        )
        prompt = f"""
Perform this preflight exactly once per step:
1. Call get_literature.
2. Run `{gpu_check}` and report whether a CUDA GPU is allocated.
3. Run `{helper} search "sycophancy language models alignment" --limit 1`.
4. Extract its arXiv id and run `{helper} fetch <that-id>`; read the returned title,
   authors, id, and visible text or labeled abstract fallback.
5. Call share_literature once with a clearly labeled disposable smoke entry based
   only on that fetched paper. Do not call any other command or network tool.
"""
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tools.append({"name": block.name, "input": block.input})
                if isinstance(message, ResultMessage):
                    if message.is_error:
                        raise RuntimeError(message.result)
                    break

        names = [item["name"] for item in tools]
        for required in (
            "mcp__server-api-tools__get_literature",
            "mcp__server-api-tools__share_literature",
        ):
            if names.count(required) != 1:
                raise RuntimeError(f"expected exactly one {required}, got {names!r}")
        commands = [str(item["input"].get("command", "")) for item in tools if item["name"] == "Bash"]
        if not any(command == str(gpu_check) for command in commands):
            raise RuntimeError(f"GPU boundary check was not called: {commands!r}")
        if not any(command.startswith(f"{helper} search ") for command in commands):
            raise RuntimeError(f"paper search was not called: {commands!r}")
        if not any(command.startswith(f"{helper} fetch ") for command in commands):
            raise RuntimeError(f"paper fetch was not called: {commands!r}")
        entries = list((root / "team_literature").glob("*.json"))
        if len(entries) != 1:
            raise RuntimeError(f"expected one shared smoke entry, found {len(entries)}")
        return {"ok": True, "tool_names": names, "commands": commands}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2))
