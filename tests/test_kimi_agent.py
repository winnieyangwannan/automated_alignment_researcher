"""Focused tests for the opt-in Kimi research-agent backend."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
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
    def test_turn_timeout_terminates_cli_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import os, subprocess, sys, time\n"
                "from pathlib import Path\n"
                "child = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(30)'])\n"
                "Path('turn-pids').write_text(f'{os.getpid()} {child.pid}')\n"
                "time.sleep(30)\n"
            )
            cli.chmod(0o755)
            result = asyncio.run(
                KimiAgent(
                    "test-agent",
                    root,
                    cli_path=str(cli),
                    turn_timeout_seconds=0.2,
                ).execute("task")
            )
            parent_pid, child_pid = map(
                int, (root / "turn-pids").read_text().split()
            )
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and any(
                Path(f"/proc/{pid}").exists() for pid in (parent_pid, child_pid)
            ):
                time.sleep(0.05)

            self.assertFalse(result.success)
            self.assertIn("turn exceeded", result.error or "")
            self.assertFalse(Path(f"/proc/{parent_pid}").exists())
            self.assertFalse(Path(f"/proc/{child_pid}").exists())

    def test_only_current_session_proposal_owns_persistent_training_state(self) -> None:
        agent = KimiAgent("test-agent", Path.cwd(), cli_path="/bin/true")
        self.assertFalse(agent._submitted_proposal_in_output({"tool_uses": []}))
        self.assertFalse(
            agent._submitted_proposal_in_output(
                {"tool_uses": [{"tool": "get_literature", "input": {}}]}
            )
        )
        self.assertTrue(
            agent._submitted_proposal_in_output(
                {
                    "tool_uses": [
                        {
                            "tool": "mcp__server-api-tools__submit_idea_proposal",
                            "input": {},
                        }
                    ]
                }
            )
        )

    def test_stale_failed_proposal_does_not_poison_new_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json\n"
                "print(json.dumps({'role': 'assistant', 'content': 'fresh session'}))\n"
            )
            cli.chmod(0o755)
            agent = KimiAgent("test-agent", root, cli_path=str(cli))
            with patch.object(
                agent,
                "_current_training_failure",
                return_value={"status": "failed", "run_id": "stale-run"},
            ):
                result = asyncio.run(agent.execute("start a new research session"))

            self.assertTrue(result.success, result.error)

    def test_pre_marker_rejection_cannot_reuse_prior_approved_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scores = root / "scores"
            proposals = scores / ".proposals"
            proposals.mkdir(parents=True)
            idea_uid = "kimi-stale-approval"
            marker = proposals / f"{idea_uid}.json"
            marker.write_text(
                json.dumps(
                    {
                        "approved": True,
                        "idea_name": "old_candidate",
                        "code_hash": "old-code",
                    }
                )
            )
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")

            with patch.dict(
                os.environ,
                {"SCORES_DIR": str(scores), "IDEA_UID": idea_uid},
                clear=False,
            ):
                agent._proposal_marker_fingerprint_at_start = (
                    agent._proposal_marker_fingerprint()
                )
                self.assertFalse(agent._proposal_marker_changed_this_session())

                # Early proposal validation errors return before writing a new
                # marker.  The durable approved marker must therefore remain
                # ineligible for training actions in this new session.
                self.assertTrue(
                    agent._submitted_proposal_in_output(
                        {
                            "tool_uses": [
                                {
                                    "tool": "submit_idea_proposal",
                                    "input": {"idea_name": "missing_candidate"},
                                }
                            ]
                        }
                    )
                )
                self.assertFalse(agent._proposal_marker_changed_this_session())

                marker.write_text(
                    json.dumps(
                        {
                            "approved": False,
                            "idea_name": "new_candidate",
                            "code_hash": "new-code",
                        }
                    )
                )
                self.assertTrue(agent._proposal_marker_changed_this_session())


    def test_successful_retry_score_takes_precedence_over_retained_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scores = root / "scores"
            proposals = scores / ".proposals"
            runs = proposals / "runs"
            receipts = root / ".train_submissions"
            runs.mkdir(parents=True)
            receipts.mkdir()
            idea_uid = "kimi-retry"
            run_id = f"{idea_uid}-candidate-1"
            marker = {
                "approved": True,
                "idea_name": "kimi_candidate",
                "code_hash": "abc123",
            }
            (proposals / f"{idea_uid}.json").write_text(json.dumps(marker))
            (runs / "candidate.json").write_text(
                json.dumps({
                    **marker,
                    "run_id": run_id,
                    "stamped_ts": 1,
                })
            )
            (receipts / f"{run_id}.env").write_text(
                f"run_id={run_id}\njob_id=12345\n"
            )
            (scores / f"{run_id}.failed.json").write_text(
                json.dumps({"error": "retained first-attempt failure"})
            )
            (scores / f"{run_id}.json").write_text(json.dumps({"score": 1.0}))

            agent = KimiAgent(
                "test-agent",
                root,
                cli_path="/bin/true",
                completion_tool="share_finding",
            )
            with patch.dict(
                os.environ,
                {
                    "SCORES_DIR": str(scores),
                    "TEAM_DIR": str(root),
                    "IDEA_UID": idea_uid,
                },
                clear=False,
            ):
                asyncio.run(agent._wait_for_training_result())

    def test_slurm_timeout_publishes_failure_instead_of_waiting_forever(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scores = root / "scores"
            proposals = scores / ".proposals"
            runs = proposals / "runs"
            receipts = root / ".train_submissions"
            runs.mkdir(parents=True)
            receipts.mkdir()
            idea_uid = "kimi-timeout"
            run_id = f"{idea_uid}-candidate-1"
            marker = {
                "approved": True,
                "idea_name": "kimi_candidate",
                "code_hash": "abc123",
            }
            (proposals / f"{idea_uid}.json").write_text(json.dumps(marker))
            (runs / "candidate.json").write_text(
                json.dumps({**marker, "run_id": run_id, "stamped_ts": 1})
            )
            (receipts / f"{run_id}.env").write_text(
                f"run_id={run_id}\njob_id=12345\n"
            )
            agent = KimiAgent(
                "test-agent",
                root,
                cli_path="/bin/true",
                completion_tool="share_finding",
            )

            with (
                patch.dict(
                    os.environ,
                    {
                        "SCORES_DIR": str(scores),
                        "TEAM_DIR": str(root),
                        "IDEA_UID": idea_uid,
                    },
                    clear=False,
                ),
                patch.object(
                    KimiAgent,
                    "_slurm_job_result",
                    return_value=("TIMEOUT", 0),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "training_slurm_timeout"):
                    asyncio.run(agent._wait_for_training_result())

            failure = json.loads((scores / f"{run_id}.failed.json").read_text())
            self.assertEqual(failure["stage"], "training")
            self.assertEqual(failure["error_code"], "training_slurm_timeout")
            self.assertEqual(failure["exit_code"], 0)
            self.assertEqual(failure["log_path"], str(root / "logs" / "train-12345.out"))

    def test_slurm_result_normalizes_signal_exit_and_state_suffix(self) -> None:
        completed = subprocess.CompletedProcess(
            ["sacct"], 0, "TIMEOUT+|0:9|\n", ""
        )
        with patch(
            "aar.research_loop.kimi_agent.subprocess.run", return_value=completed
        ):
            self.assertEqual(KimiAgent._slurm_job_result("12345"), ("TIMEOUT", 137))

    def test_previous_failure_is_injected_into_next_kimi_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scores = root / "scores"
            proposals = scores / ".proposals"
            runs = proposals / "runs"
            runs.mkdir(parents=True)
            idea_uid = "kimi-feedback"
            run_id = f"{idea_uid}-candidate-1"
            marker = {
                "approved": True,
                "idea_name": "kimi_candidate",
                "code_hash": "abc123",
            }
            (proposals / f"{idea_uid}.json").write_text(json.dumps(marker))
            (runs / "candidate.json").write_text(
                json.dumps(
                    {
                        **marker,
                        "run_id": run_id,
                        "stamped_ts": 1,
                    }
                )
            )
            failure = {
                "schema_version": 2,
                "status": "failed",
                "run_id": run_id,
                "stage": "training",
                "error_code": "training_python_exception",
                "exception_type": "TypeError",
                "error": "unexpected keyword argument 'tokenizer'",
                "retryable": False,
                "log_path": str(root / "logs" / "train-123.out"),
            }
            (scores / f"{run_id}.failed.json").write_text(json.dumps(failure))
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")

            with patch.dict(
                os.environ,
                {"SCORES_DIR": str(scores), "IDEA_UID": idea_uid},
                clear=False,
            ):
                prompt = agent._with_previous_failure_feedback("do research")
                self.assertIn("AUTOMATIC HELD-OUT-SAFE FAILURE FEEDBACK", prompt)
                self.assertIn("training_python_exception", prompt)
                self.assertIn("unexpected keyword argument", prompt)
                self.assertIn("train-123.out", prompt)

                (scores / f"{run_id}.json").write_text("{}\n")
                self.assertEqual(
                    agent._with_previous_failure_feedback("do research"),
                    "do research",
                )

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
                        "stop": "END",
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
        self.assertEqual(
            observed["payload"]["stop"],
            ["END", "!!!!!!!!!!!!!!!!"],
        )

    def test_opt_in_proxy_forces_one_named_checkpoint_tool(self) -> None:
        observed = []

        class UpstreamHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                observed.append(json.loads(self.rfile.read(length)))
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
        env = {
            "KIMI_MODEL_BASE_URL": f"http://127.0.0.1:{upstream.server_port}/v1",
            "KIMI_MODEL_API_KEY": "secret",
        }
        agent = KimiAgent(
            "test-agent",
            Path.cwd(),
            cli_path="/bin/true",
            force_checkpoint_tools=True,
        )
        try:
            with agent._request_policy_proxy(env) as controller:
                controller.arm("Bash")
                request = {
                    "model": "Kimi-K2.6",
                    "tools": [
                        {"type": "function", "function": {"name": "Read"}},
                        {"type": "function", "function": {"name": "Bash"}},
                    ],
                }
                for _ in range(2):
                    response = requests.post(
                        f"{env['KIMI_MODEL_BASE_URL']}/chat/completions",
                        json=request,
                        timeout=5,
                    )
                    response.raise_for_status()
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)

        self.assertEqual(observed[0]["tool_choice"], "required")
        self.assertEqual(
            observed[0]["tools"],
            [{"type": "function", "function": {"name": "Bash"}}],
        )
        self.assertNotIn("tool_choice", observed[1])

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

    def test_rejected_share_finding_is_not_completion_when_result_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            team = Path(temp)
            run_id = "chain-candidate-1"
            agent = KimiAgent(
                "test-agent",
                Path.cwd(),
                cli_path="/bin/true",
                completion_tool="share_finding",
            )
            output = {
                "tool_uses": [
                    {
                        "tool": "mcp__server-api-tools__share_finding",
                        "input": {"run_id": run_id},
                    }
                ]
            }
            with (
                patch.dict(
                    os.environ,
                    {
                        "AAR_REQUIRE_SUCCESSFUL_ITERATIONS": "1",
                        "TEAM_DIR": str(team),
                    },
                ),
                patch.object(agent, "_approved_run_id", return_value=run_id),
            ):
                self.assertFalse(agent._completion_tool_used(output))
                registry = (
                    team
                    / ".finding_dedup"
                    / f"runid_{run_id}"
                    / "post.json"
                )
                registry.parent.mkdir(parents=True)
                registry.write_text(json.dumps({"post_id": "post-1"}))
                self.assertTrue(agent._completion_tool_used(output))

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

            empty_output = {"tool_uses": []}
            self.assertIn("get_literature", agent._continuation_prompt(empty_output))
            self.assertEqual(agent._continuation_tool(empty_output), "get_literature")
            literature = (
                "mcp__server-api-tools__get_literature",
                {},
            )

            def prompt(*uses: tuple[str, dict[str, str]]) -> str:
                return agent._continuation_prompt(
                    {
                        "tool_uses": [
                            {"tool": tool, "input": tool_input}
                            for tool, tool_input in (literature, *uses)
                        ]
                    }
                )

            def forced_tool(*uses: tuple[str, dict[str, str]]) -> str | None:
                return agent._continuation_tool(
                    {
                        "tool_uses": [
                            {"tool": tool, "input": tool_input}
                            for tool, tool_input in (literature, *uses)
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
            validate = (
                "Bash",
                {"command": f"python scripts/validate_method_contract.py {method}"},
            )
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
                {
                    "AAR_IDEAS_DIR": str(ideas),
                    "IDEA_NAME": "test-chain",
                    "IDEA_UID": "test-chain-uid",
                    "SCORES_DIR": str(root),
                    "TEAM_DIR": str(root),
                },
            ):
                self.assertIn("Read tool exactly once", prompt())
                self.assertEqual(forced_tool(), "Read")
                self.assertIn("candidate scaffold", prompt(read))
                self.assertEqual(forced_tool(read), "Bash")
                self.assertIn("Write tool exactly once", prompt(read, scaffold))
                self.assertEqual(forced_tool(read, scaffold), "Write")
                self.assertIn(
                    "validate_method_contract.py", prompt(read, scaffold, write)
                )
                self.assertEqual(forced_tool(read, scaffold, write), "Bash")
                Path(method).parent.mkdir(parents=True, exist_ok=True)
                Path(method).write_text("method code")
                proof = Path(method).parent / ".aar-method-contract.json"
                proof.write_text(
                    json.dumps(
                        {
                            "status": "passed",
                            "source_sha256": hashlib.sha256(
                                Path(method).read_bytes()
                            ).hexdigest(),
                            "errors": [],
                        }
                    )
                )
                self.assertIn(
                    "submit_idea_proposal",
                    prompt(read, scaffold, write, validate),
                )
                self.assertEqual(
                    forced_tool(read, scaffold, write, validate),
                    "submit_idea_proposal",
                )
                proposal_dir = root / ".proposals"
                proposal_dir.mkdir()
                marker = proposal_dir / "test-chain-uid.json"
                marker.write_text(
                    json.dumps(
                        {
                            "approved": False,
                            "idea_name": module,
                            "code_hash": "hash-1",
                        }
                    )
                )
                rejection_prompt = prompt(read, scaffold, write, validate, proposal)
                self.assertIn(f"path={json.dumps(method)}", rejection_prompt)
                self.assertIn("Do not create or write another candidate", rejection_prompt)
                self.assertEqual(
                    forced_tool(read, scaffold, write, validate, proposal),
                    "Write",
                )
                marker.write_text(
                    json.dumps(
                        {
                            "approved": False,
                            "idea_name": module,
                            "code_hash": hashlib.sha256(
                                Path(method).read_bytes()
                            ).hexdigest(),
                            "verdict": {
                                "code_diverges_from_proposal": False,
                                "reproducible_from_paper": False,
                                "missing_for_reproduction": ["exact loss masking"],
                            },
                        }
                    )
                )
                paper_prompt = prompt(read, scaffold, write, validate, proposal)
                self.assertIn("missing_for_reproduction", paper_prompt)
                self.assertEqual(
                    forced_tool(read, scaffold, write, validate, proposal),
                    "submit_idea_proposal",
                )
                marker.write_text(
                    json.dumps(
                        {
                            "approved": True,
                            "idea_name": module,
                            "code_hash": "hash-1",
                        }
                    )
                )
                runs = proposal_dir / "runs"
                runs.mkdir()
                (runs / "test-chain-uid-run-1.json").write_text(
                    json.dumps(
                        {
                            "run_id": "test-chain-uid-run-1",
                            "idea_name": module,
                            "code_hash": "hash-1",
                            "stamped_ts": 1,
                        }
                    )
                )
                self.assertIn(
                    "submit_train_job.sh",
                    prompt(read, scaffold, write, validate, proposal),
                )
                self.assertEqual(
                    forced_tool(read, scaffold, write, validate, proposal),
                    "Bash",
                )
                receipt = root / ".train_submissions" / "test-chain-uid-run-1.env"
                receipt.parent.mkdir()
                receipt.write_text("run_id=test-chain-uid-run-1\njob_id=12345\n")
                self.assertIn(
                    "foreground-poll",
                    prompt(read, scaffold, write, validate, proposal, training),
                )
                self.assertEqual(
                    forced_tool(read, scaffold, write, validate, proposal, training),
                    "Bash",
                )
                score.write_text('{"composite": 0.1}\n')
                with patch.object(
                    agent, "_score_path_for_run", return_value=score
                ):
                    self.assertIn(
                        "Read tool exactly once",
                        prompt(read, scaffold, write, validate, proposal, training),
                    )
                    self.assertEqual(
                        forced_tool(
                            read, scaffold, write, validate, proposal, training
                        ),
                        "Read",
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
                    self.assertEqual(
                        forced_tool(
                            read,
                            scaffold,
                            write,
                            validate,
                            proposal,
                            training,
                            score_read,
                        ),
                        "share_finding",
                    )

    def test_autodata_continuation_reads_reviewed_recipe_before_template(self) -> None:
        agent = KimiAgent(
            "test-agent",
            Path.cwd(),
            cli_path="/bin/true",
            completion_tool="share_finding",
        )
        recipe_root = Path("/tmp/reviewed-autodata-recipe")
        literature = {
            "tool_uses": [
                {
                    "tool": "mcp__server-api-tools__get_literature",
                    "input": {},
                }
            ]
        }
        with patch.dict(
            os.environ,
            {
                "AAR_AUTODATA": "1",
                "AAR_AUTODATA_RECIPE_ROOT": str(recipe_root),
            },
        ):
            recipe_prompt = agent._continuation_prompt(literature)
            self.assertIn("judge_rubric.json", recipe_prompt)
            self.assertIn("recipe/task.py", recipe_prompt)
            self.assertEqual(agent._continuation_tool(literature), "Bash")

            recipe_command = " ".join(
                str(recipe_root / relative)
                for relative in (
                    "autodata.pipeline.json",
                    "objective.json",
                    "comparator.json",
                    "grounding/coverage.json",
                    "recipe/generation_strategy.json",
                    "recipe/judge_rubric.json",
                    "recipe/request.json",
                    "recipe/task.py",
                )
            )
            after_recipe = {
                "tool_uses": [
                    *literature["tool_uses"],
                    {"tool": "Bash", "input": {"command": recipe_command}},
                ]
            }
            self.assertIn(
                "native Read tool exactly once",
                agent._continuation_prompt(after_recipe),
            )

    def test_approved_training_submission_is_adapter_controlled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal_dir = root / "scores" / ".proposals"
            runs = proposal_dir / "runs"
            runs.mkdir(parents=True)
            marker = {
                "approved": True,
                "idea_name": "chain__kimi_candidate",
                "code_hash": "hash-1",
            }
            (proposal_dir / "chain-uid.json").write_text(json.dumps(marker))
            run_id = "chain-uid-chain__kimi_candidate-1"
            (runs / f"{run_id}.json").write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "idea_name": "chain__kimi_candidate",
                        "code_hash": "hash-1",
                        "stamped_ts": 1,
                    }
                )
            )
            receipt = root / "team" / ".train_submissions" / f"{run_id}.env"

            def submit(command, **kwargs):
                self.assertEqual(command[-2:], ["chain__kimi_candidate", run_id])
                self.assertFalse(kwargs.get("shell", False))
                receipt.parent.mkdir(parents=True)
                receipt.write_text(f"run_id={run_id}\njob_id=12345\n")
                return subprocess.CompletedProcess(command, 0, "12345\n", "")

            agent = KimiAgent(
                "test-agent", root, cli_path="/bin/true", completion_tool="share_finding"
            )
            with (
                patch.dict(
                    os.environ,
                    {
                        "AAR_REQUIRE_TRAIN_RECEIPT": "1",
                        "SCORES_DIR": str(root / "scores"),
                        "TEAM_DIR": str(root / "team"),
                        "IDEA_UID": "chain-uid",
                    },
                ),
                patch("aar.research_loop.kimi_agent.subprocess.run", side_effect=submit),
            ):
                agent._ensure_approved_training_submission()

            self.assertEqual(receipt.read_text(), f"run_id={run_id}\njob_id=12345\n")

    def test_autodata_approval_defers_training_until_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scores = root / "scores"
            proposal_dir = scores / ".proposals"
            runs = proposal_dir / "runs"
            runs.mkdir(parents=True)
            run_id = "chain-uid-chain__kimi_candidate-1"
            marker = {
                "approved": True,
                "idea_name": "chain__kimi_candidate",
                "code_hash": "hash-1",
            }
            (proposal_dir / "chain-uid.json").write_text(json.dumps(marker))
            (runs / f"{run_id}.json").write_text(
                json.dumps(
                    {
                        **marker,
                        "run_id": run_id,
                        "stamped_ts": 1,
                    }
                )
            )
            team = root / "team"
            receipt = team / ".train_submissions" / f"{run_id}.env"

            def submit(command, **kwargs):
                receipt.parent.mkdir(parents=True)
                receipt.write_text(f"run_id={run_id}\njob_id=12345\n")
                return subprocess.CompletedProcess(command, 0, "12345\n", "")

            agent = KimiAgent(
                "test-agent", root, cli_path="/bin/true", completion_tool="share_finding"
            )
            environment = {
                "AAR_AUTODATA": "1",
                "AAR_REQUIRE_TRAIN_RECEIPT": "1",
                "SCORES_DIR": str(scores),
                "TEAM_DIR": str(team),
                "IDEA_UID": "chain-uid",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch(
                    "aar.research_loop.kimi_agent.subprocess.run", side_effect=submit
                ) as run,
            ):
                agent._ensure_approved_training_submission()
                run.assert_not_called()
                self.assertFalse(receipt.exists())

                handoff = team / "autodata" / run_id / "training-handoff.json"
                handoff.parent.mkdir(parents=True)
                handoff.write_text("{}\n")
                agent._ensure_approved_training_submission()
                run.assert_called_once()

            self.assertEqual(receipt.read_text(), f"run_id={run_id}\njob_id=12345\n")

    def test_autodata_continuation_resumes_approved_run_before_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal_dir = root / ".proposals"
            runs = proposal_dir / "runs"
            runs.mkdir(parents=True)
            run_id = "chain-uid-chain__kimi_candidate-1"
            marker = {
                "approved": True,
                "idea_name": "chain__kimi_candidate",
                "code_hash": "hash-1",
            }
            (proposal_dir / "chain-uid.json").write_text(json.dumps(marker))
            (runs / f"{run_id}.json").write_text(
                json.dumps({**marker, "run_id": run_id, "stamped_ts": 1})
            )
            agent = KimiAgent(
                "test-agent",
                Path.cwd(),
                cli_path="/bin/true",
                completion_tool="share_finding",
            )
            output = {
                "tool_uses": [
                    {
                        "tool": "mcp__server-api-tools__submit_idea_proposal",
                        "input": {"idea_name": "chain__kimi_candidate"},
                    }
                ]
            }
            with patch.dict(
                os.environ,
                {
                    "AAR_AUTODATA": "1",
                    "AAR_IDEAS_DIR": str(root / "methods"),
                    "IDEA_NAME": "chain",
                    "IDEA_UID": "chain-uid",
                    "SCORES_DIR": str(root),
                    "TEAM_DIR": str(root / "team"),
                },
                clear=False,
            ):
                prompt = agent._continuation_prompt(output)
                self.assertIn("proposal is already approved", prompt)
                self.assertIn(run_id, prompt)
                self.assertIn("training-handoff.json", prompt)
                self.assertNotIn("submit_train_job.sh", prompt)
                self.assertIsNone(agent._continuation_tool(output))

                bootstrap = (
                    root
                    / "team"
                    / "autodata"
                    / run_id
                    / "workspace-bootstrap.json"
                )
                bootstrap.parent.mkdir(parents=True)
                workspace_id = "ws_" + "1" * 32
                bootstrap.write_text(json.dumps({"workspace_id": workspace_id}))
                bootstrapped_prompt = agent._continuation_prompt(output)
                self.assertIn("trusted orchestration already created", bootstrapped_prompt)
                self.assertIn(workspace_id, bootstrapped_prompt)
                self.assertIn("Do not load a skill", bootstrapped_prompt)
                self.assertNotIn("create or resume", bootstrapped_prompt)

                with patch.dict(
                    os.environ, {"AAR_RESUME_APPROVED_PROPOSAL": "1"}, clear=False
                ):
                    resumed = agent._with_resumable_approved_run("original task")
                    self.assertIn("AUTOMATIC RESUME CONTEXT", resumed)
                    self.assertIn(run_id, resumed)

    def test_standard_mcp_bridge_advertises_existing_tool_objects(self) -> None:
        names = {tool.name for tool in SERVER_TOOLS["server-api-tools"]}
        self.assertIn("evaluate_model", names)
        self.assertIn("review_autodata_action", names)
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
