"""Focused tests for the opt-in Kimi research-agent backend."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests

from aar.research_loop.kimi_agent import KimiAgent, KimiToolUseBlock
from aar.research_loop.tools.kimi_mcp_server import (
    SERVER_TOOLS,
    _text_content,
    create_server,
)
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
                "print('terminal output that is not JSON')\n"
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
            self.assertEqual(
                result.output["raw_stdout"], ["terminal output that is not JSON"]
            )
            self.assertIsInstance(callbacks[0].content[1], KimiToolUseBlock)
            self.assertNotIn("stderr", result.output)

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

    def test_serve_api_provider_is_resolved_for_each_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            serve_root = root / "serve_api_v2"
            serve_root.mkdir()
            serve = serve_root / "serve.sh"
            serve.write_text(
                f"#!{sys.executable}\n"
                "import json, sys\n"
                "assert sys.argv[1:] == ['generate-opencode-config', 'test-deployment']\n"
                "print(json.dumps({'provider': {'test': {\n"
                "  'options': {'baseURL': 'http://proxy.example/v1', 'apiKey': 'secret'},\n"
                "  'models': {'Kimi-K2.6': {}}\n"
                "}}}))\n"
            )
            serve.chmod(0o755)
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")
            with patch.dict(
                os.environ,
                {
                    "AAR_KIMI_SERVE_DEPLOYMENT": "test-deployment",
                    "AAR_KIMI_EXPECTED_MODEL": "Kimi-K2.6",
                    "AAR_SERVE_API_V2_ROOT": str(serve_root),
                },
                clear=False,
            ):
                env = agent._build_environment(root)

            self.assertEqual(env["KIMI_MODEL_NAME"], "Kimi-K2.6")
            self.assertEqual(env["KIMI_MODEL_PROVIDER_TYPE"], "openai")
            self.assertEqual(env["KIMI_MODEL_BASE_URL"], "http://proxy.example/v1")
            self.assertEqual(env["KIMI_MODEL_API_KEY"], "secret")
            self.assertEqual(env["KIMI_MODEL_MAX_CONTEXT_SIZE"], "262144")
            self.assertEqual(env["KIMI_MODEL_MAX_OUTPUT_SIZE"], "65536")
            self.assertEqual(env["KIMI_MODEL_MAX_COMPLETION_TOKENS"], "65536")
            self.assertEqual(env["KIMI_MODEL_CAPABILITIES"], "thinking,tool_use")
            self.assertEqual(env["KIMI_MODEL_REASONING_KEY"], "reasoning_content")

            kimi_env = {
                "AAR_KIMI_SERVE_DEPLOYMENT": "test-deployment",
                "AAR_KIMI_EXPECTED_MODEL": "Kimi-K2.6",
                "AAR_KIMI_PROVIDER_TYPE": "kimi",
                "AAR_SERVE_API_V2_ROOT": str(serve_root),
            }
            agent._apply_serve_api_provider(kimi_env)
            self.assertEqual(kimi_env["KIMI_MODEL_PROVIDER_TYPE"], "kimi")

    def test_system_prompt_uses_agent_profile_and_disables_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kimi_home = root / "kimi-home"
            kimi_home.mkdir()
            capture = root / "capture.json"
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "index = sys.argv.index('--agent-file')\n"
                "profile = Path(sys.argv[index + 1])\n"
                "home = Path(os.environ['KIMI_CODE_HOME'])\n"
                "Path(os.environ['KIMI_TEST_CAPTURE']).write_text(json.dumps({\n"
                "  'argv': sys.argv[1:], 'profile': profile.read_text(),\n"
                "  'config': (home / 'config.toml').read_text(),\n"
                "}))\n"
                "print(json.dumps({'role': 'assistant', 'content': 'done'}))\n"
            )
            cli.chmod(0o755)
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
                        root,
                        cli_path=str(cli),
                        system_prompt="System-level AAR instructions.",
                        disallowed_tools=["CreateGoal", "AgentSwarm"],
                        auto_approve=True,
                    ).execute("research task")
                )

            self.assertTrue(result.success, result.error)
            observed = json.loads(capture.read_text())
            self.assertIn("--agent-file", observed["argv"])
            self.assertNotIn("--auto", observed["argv"])
            self.assertIn(
                'defaultPermissionMode = "auto"', observed["config"]
            )
            self.assertNotIn("System-level AAR instructions.", observed["argv"])
            self.assertIn(
                'disallowedTools: ["CreateGoal", "AgentSwarm"]',
                observed["profile"],
            )
            self.assertIn("System-level AAR instructions.", observed["profile"])

    def test_serve_api_provider_rejects_unexpected_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            serve = root / "serve.sh"
            serve.write_text(
                f"#!{sys.executable}\n"
                "import json\n"
                "print(json.dumps({'provider': {'test': {\n"
                "  'options': {'baseURL': 'http://proxy.example/v1', 'apiKey': 'secret'},\n"
                "  'models': {'wrong-model': {}}\n"
                "}}}))\n"
            )
            serve.chmod(0o755)
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")
            with patch.dict(
                os.environ,
                {
                    "AAR_KIMI_SERVE_DEPLOYMENT": "test-deployment",
                    "AAR_KIMI_EXPECTED_MODEL": "Kimi-K2.6",
                    "AAR_SERVE_API_V2_ROOT": str(root),
                },
                clear=False,
            ):
                with self.assertRaisesRegex(RuntimeError, "model mismatch"):
                    agent._build_environment(root)

    def test_opt_in_proxy_disables_thinking_and_hides_upstream_key(self) -> None:
        observed = {}

        class UpstreamHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                observed["path"] = self.path
                observed["authorization"] = self.headers["Authorization"]
                observed["payload"] = json.loads(self.rfile.read(length))
                response = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, _format: str, *args: object) -> None:
                return

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        original_url = f"http://127.0.0.1:{upstream.server_port}/v1"
        env = {
            "AAR_KIMI_DISABLE_THINKING": "1",
            "KIMI_MODEL_BASE_URL": original_url,
            "KIMI_MODEL_API_KEY": "upstream-secret",
        }
        agent = KimiAgent("test-agent", Path.cwd(), cli_path="/bin/true")
        try:
            with agent._request_policy_proxy(env):
                self.assertTrue(
                    env["KIMI_MODEL_BASE_URL"].startswith("http://127.0.0.1:")
                )
                self.assertNotEqual(env["KIMI_MODEL_BASE_URL"], original_url)
                self.assertEqual(
                    env["KIMI_MODEL_API_KEY"], "aar-local-request-policy"
                )
                response = requests.post(
                    f"{env['KIMI_MODEL_BASE_URL']}/chat/completions",
                    headers={"Authorization": "Bearer child-visible-key"},
                    json={
                        "model": "Kimi-K2.6",
                        "chat_template_kwargs": {"other": "preserved"},
                    },
                    timeout=5,
                )
                response.raise_for_status()
                self.assertEqual(response.json(), {"ok": True})
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)

        self.assertEqual(env["KIMI_MODEL_BASE_URL"], original_url)
        self.assertEqual(env["KIMI_MODEL_API_KEY"], "upstream-secret")
        self.assertEqual(observed["path"], "/v1/chat/completions")
        self.assertEqual(observed["authorization"], "Bearer upstream-secret")
        self.assertEqual(
            observed["payload"]["chat_template_kwargs"],
            {"other": "preserved", "enable_thinking": False},
        )

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

    def test_incomplete_kimi_turn_resumes_until_completion_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "counter = Path(os.environ['KIMI_CODE_HOME']) / 'test-calls'\n"
                "call = int(counter.read_text()) + 1 if counter.exists() else 1\n"
                "counter.write_text(str(call))\n"
                "if call == 1:\n"
                "  assert '--continue' not in sys.argv\n"
                "  print(json.dumps({'role': 'assistant', 'content': 'Let me continue.'}))\n"
                "else:\n"
                "  assert '--continue' in sys.argv\n"
                "  print(json.dumps({'role': 'assistant', 'content': 'done', "
                "'tool_calls': [{'function': {'name': "
                "'mcp__server-api-tools__share_finding', 'arguments': '{}'}}]}))\n"
            )
            cli.chmod(0o755)
            result = asyncio.run(
                KimiAgent(
                    "test-agent",
                    root,
                    cli_path=str(cli),
                    completion_tool="share_finding",
                ).execute("complete the task")
            )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output["continuations"], 1)
        self.assertEqual(result.iteration_count, 1)
        self.assertEqual(result.output["text_outputs"], ["Let me continue.", "done"])

    def test_share_finding_continuations_advance_missing_milestone(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ideas = root / "methods"
            ideas.mkdir()
            score = root / "score.json"
            agent = KimiAgent(
                "test-agent",
                Path.cwd(),
                cli_path="/bin/true",
                completion_tool="share_finding",
            )

            def prompt(*uses: tuple[str, dict[str, str]]) -> str:
                return agent._continuation_prompt(
                    {
                        "tool_uses": [
                            {"tool": tool, "input": tool_input}
                            for tool, tool_input in uses
                        ]
                    }
                )

            template = str(Path.cwd() / "aar/ideas/TEMPLATE/run.py")
            module = "test_chain__kimi_candidate"
            method = str(ideas / module / "run.py")
            read = ("Read", {"path": template})
            scaffold = (
                "Bash",
                {"command": f"cp -a aar/ideas/TEMPLATE/. {ideas / module}/"},
            )
            write = ("Write", {"path": method, "content": "method code"})
            validate = ("Bash", {"command": f"python -m py_compile {method}"})
            proposal = (
                "mcp__server-api-tools__submit_idea_proposal",
                {"idea_name": "candidate"},
            )
            training = (
                "Bash",
                {"command": f"scripts/submit_train_job.sh {module} run-id"},
            )

            with patch.dict(
                os.environ,
                {"AAR_IDEAS_DIR": str(ideas), "IDEA_NAME": "test-chain"},
            ):
                self.assertIn("Read tool exactly once", prompt())
                self.assertIn("candidate scaffold", prompt(read))
                self.assertIn("Write tool exactly once", prompt(read, scaffold))
                self.assertIn("py_compile", prompt(read, scaffold, write))
                self.assertIn(
                    "submit_idea_proposal",
                    prompt(read, scaffold, write, validate),
                )
                self.assertIn(
                    "submit_train_job.sh",
                    prompt(read, scaffold, write, validate, proposal),
                )
                self.assertIn(
                    "foreground-poll",
                    prompt(read, scaffold, write, validate, proposal, training),
                )
                score.write_text('{"composite": 0.1}\n')
                with patch.object(
                    agent, "_current_score_path", return_value=score
                ):
                    self.assertIn(
                        "Read tool exactly once",
                        prompt(read, scaffold, write, validate, proposal, training),
                    )
                    score_read = ("Read", {"path": str(score)})
                    self.assertIn(
                        "share_finding",
                        prompt(
                            read,
                            scaffold,
                            write,
                            validate,
                            proposal,
                            training,
                            score_read,
                        ),
                    )

    def test_standard_mcp_bridge_advertises_existing_tool_objects(self) -> None:
        self.assertIn("evaluate_model", {
            tool.name for tool in SERVER_TOOLS["server-api-tools"]
        })
        options = create_server("server-api-tools").create_initialization_options()
        self.assertIsNotNone(options.capabilities.tools)

    def test_standard_mcp_bridge_emits_typed_text_content(self) -> None:
        content = _text_content({"status": "ok"})
        self.assertEqual(content[0].type, "text")
        self.assertIn('"status": "ok"', content[0].text)

    def test_kimi_mcp_bridge_bounds_literature_at_entry_boundaries(self) -> None:
        payload = {
            "count": 10,
            "mode": "summary",
            "literature": [
                {"method": f"method-{index}", "summary": "x" * 500}
                for index in range(10)
            ],
        }
        value = {
            "content": [
                {"type": "text", "text": json.dumps(payload, indent=2)}
            ]
        }
        with patch.dict(
            os.environ, {"AAR_KIMI_MCP_MAX_TEXT_CHARS": "2000"}
        ):
            content = _text_content(value)

        self.assertLessEqual(len(content[0].text), 2000)
        bounded = json.loads(content[0].text)
        self.assertTrue(bounded["aar_kimi_bridge"]["truncated"])
        self.assertEqual(bounded["aar_kimi_bridge"]["original_entries"], 10)
        self.assertLess(bounded["aar_kimi_bridge"]["returned_entries"], 10)
        self.assertEqual(
            bounded["aar_kimi_bridge"]["returned_entries"],
            len(bounded["literature"]),
        )


if __name__ == "__main__":
    unittest.main()
