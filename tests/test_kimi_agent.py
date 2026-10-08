"""Focused tests for the opt-in Kimi research-agent backend."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from aar.research_loop.kimi_agent import KimiAgent, KimiToolUseBlock
from aar.research_loop.tools.kimi_mcp_server import SERVER_TOOLS, create_server
import run as launcher


class KimiAgentTest(unittest.TestCase):
    def test_launcher_selects_kimi_without_anthropic_credentials(self) -> None:
        observed = {}

        class Loop:
            def __init__(self, **kwargs):
                observed.update(kwargs)

            async def run(self):
                return {}

        module = types.ModuleType("aar.research_loop.agent")
        module.AutonomousAgentLoop = Loop
        args = types.SimpleNamespace(
            backend="kimi",
            idea_uid="kimi-smoke",
            idea_name="kimi smoke",
            max_runtime=60,
            max_iterations=1,
            model=None,
            local=True,
        )
        with (
            patch.dict(
                os.environ,
                {"KIMI_CLI_PATH": "/bin/true", "KIMI_AGENT_MODEL": "kimi-test"},
                clear=True,
            ),
            patch.dict(sys.modules, {"aar.research_loop.agent": module}),
        ):
            launcher.cmd_agent(args, [])

        self.assertEqual(observed["backend"], "kimi")
        self.assertEqual(observed["model"], "kimi-test")

    def test_stream_json_and_isolated_mcp_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            kimi_home = root / "kimi-home"
            kimi_home.mkdir()
            original_mcp = {
                "mcpServers": {"existing": {"command": "/bin/true"}}
            }
            (kimi_home / "mcp.json").write_text(json.dumps(original_mcp))
            (kimi_home / "config.toml").write_text("default_model = 'test'\n")
            capture = root / "capture.json"
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "home = Path(os.environ['KIMI_CODE_HOME'])\n"
                "Path(os.environ['KIMI_TEST_CAPTURE']).write_text(json.dumps({\n"
                "  'argv': sys.argv[1:],\n"
                "  'mcp': json.loads((home / 'mcp.json').read_text()),\n"
                "  'config_is_link': (home / 'config.toml').is_symlink(),\n"
                "}))\n"
                "print(json.dumps({'role': 'assistant', 'content': 'working', "
                "'tool_calls': [{'function': {'name': 'Bash', "
                "'arguments': '{\\\"command\\\": \\\"pwd\\\"}'}}]}))\n"
                "print(json.dumps({'role': 'tool', 'tool_call_id': '1', "
                "'content': 'ok'}))\n"
                "print(json.dumps({'role': 'assistant', 'content': 'done'}))\n"
            )
            cli.chmod(0o755)
            callbacks = []

            with patch.dict(
                os.environ,
                {
                    "KIMI_CODE_HOME": str(kimi_home),
                    "KIMI_TEST_CAPTURE": str(capture),
                },
                clear=False,
            ):
                result = asyncio.run(
                    KimiAgent(
                        "test-agent",
                        workspace,
                        model="kimi-test",
                        cli_path=str(cli),
                        message_callback=callbacks.append,
                        include_prior_work=True,
                    ).execute("research task")
                )

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.iteration_count, 1)
            self.assertEqual(result.output["text_outputs"], ["working", "done"])
            self.assertIsInstance(callbacks[0].content[1], KimiToolUseBlock)

            observed = json.loads(capture.read_text())
            self.assertEqual(
                observed["argv"],
                [
                    "--model",
                    "kimi-test",
                    "--prompt",
                    "research task",
                    "--output-format",
                    "stream-json",
                ],
            )
            self.assertNotIn("--auto", observed["argv"])
            self.assertTrue(observed["config_is_link"])
            self.assertEqual(
                set(observed["mcp"]["mcpServers"]),
                {"existing", "server-api-tools", "prior-work-tools"},
            )
            self.assertEqual(json.loads((kimi_home / "mcp.json").read_text()), original_mcp)

    def test_nonzero_cli_exit_is_a_failed_agent_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(f"#!{sys.executable}\nimport sys\nsys.stderr.write('bad auth')\nsys.exit(7)\n")
            cli.chmod(0o755)
            result = asyncio.run(
                KimiAgent("test-agent", root, cli_path=str(cli)).execute("task")
            )
        self.assertFalse(result.success)
        self.assertIn("status 7", result.error or "")
        self.assertIn("bad auth", result.error or "")

    def test_standard_mcp_bridge_advertises_existing_tool_objects(self) -> None:
        self.assertIn("evaluate_model", {
            tool.name for tool in SERVER_TOOLS["server-api-tools"]
        })
        options = create_server("server-api-tools").create_initialization_options()
        self.assertIsNotNone(options.capabilities.tools)


if __name__ == "__main__":
    unittest.main()
