"""Expose AAR's existing Claude SDK tools through standard MCP stdio."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .prior_work_tools import download_snapshot
from .server_api_tools import (
    evaluate_model,
    evaluate_predictions,
    get_leaderboard,
    get_literature,
    share_finding,
    share_literature,
    submit_idea_proposal,
)


SERVER_TOOLS = {
    "server-api-tools": [
        evaluate_model,
        evaluate_predictions,
        share_finding,
        get_leaderboard,
        get_literature,
        share_literature,
        submit_idea_proposal,
    ],
    "prior-work-tools": [download_snapshot],
}


def _json_schema(schema: Any) -> dict[str, Any]:
    """Normalize the two schema forms accepted by claude_agent_sdk.tool."""
    if not isinstance(schema, dict):
        return {"type": "object"}
    if "type" in schema:
        return schema
    python_types = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    return {
        "type": "object",
        "properties": {
            name: {"type": python_types.get(value, "string")}
            for name, value in schema.items()
        },
    }


def _text_content(value: Any) -> list[types.TextContent]:
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, list):
            converted = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    converted.append(
                        types.TextContent(
                            type="text", text=str(item.get("text", ""))
                        )
                    )
            if converted:
                return converted
    return [
        types.TextContent(
            type="text", text=json.dumps(value, default=str)
        )
    ]


def create_server(name: str) -> Server:
    if name not in SERVER_TOOLS:
        raise ValueError(f"Unknown MCP server: {name}")
    tools = {tool.name: tool for tool in SERVER_TOOLS[name]}

    tool_definitions = [
        types.Tool(
            name=tool.name,
            description=tool.description,
            inputSchema=_json_schema(tool.input_schema),
        )
        for tool in tools.values()
    ]

    async def list_tools(_context, _params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tool_definitions)

    async def call_tool(_context, params) -> types.CallToolResult:
        tool = tools.get(params.name)
        if tool is None:
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text", text=f"Unknown tool: {params.name}"
                    )
                ],
                isError=True,
            )
        try:
            result = await tool.handler(params.arguments or {})
        except Exception as error:
            return types.CallToolResult(
                content=[
                    types.TextContent(type="text", text=f"Tool failed: {error}")
                ],
                isError=True,
            )
        return types.CallToolResult(content=_text_content(result))

    try:
        # MCP SDK versions used by Claude-compatible development environments.
        return Server(
            name,
            version="1.0.0",
            on_list_tools=list_tools,
            on_call_tool=call_tool,
        )
    except TypeError as error:
        if "on_list_tools" not in str(error):
            raise

    # MCP SDK 1.x registers handlers through decorators instead of constructor
    # callbacks. The ARM64 locked evaluation environment uses this API.
    server = Server(name, version="1.0.0")

    @server.list_tools()
    async def list_tools_v1() -> list[types.Tool]:
        return tool_definitions

    @server.call_tool()
    async def call_tool_v1(
        tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        params = types.CallToolRequestParams(name=tool_name, arguments=arguments)
        return await call_tool(None, params)

    return server


async def serve(name: str) -> None:
    server = create_server(name)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, choices=sorted(SERVER_TOOLS))
    args = parser.parse_args()
    asyncio.run(serve(args.server))


if __name__ == "__main__":
    main()
