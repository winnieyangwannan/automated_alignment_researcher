"""Focused, dependency-free checks for the one-iteration smoke wiring."""

from __future__ import annotations

import asyncio
import importlib
import os
import subprocess
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from aar import config, transport
from aar.benchmarks.composite import contains_held_out, strip_held_out
from aar.ideas.TEMPLATE.run import MethodConfig
from aar.web_ui.backend import eval_orchestration
import run as launcher


def _write_submission(path: Path, *, tokenizer: bool = True) -> None:
    path.mkdir()
    (path / "config.json").write_text("{}")
    (path / "model.safetensors").write_bytes(b"weights")
    if tokenizer:
        (path / "tokenizer_config.json").write_text("{}")
        (path / "tokenizer.json").write_text("{}")


class SmokeOrchestrationTest(TestCase):
    def test_agent_cli_exports_chain_identity_before_tool_initialization(self):
        observed = {}

        class Loop:
            def __init__(self, **kwargs):
                observed.update(kwargs)
                observed["env_uid"] = os.getenv("IDEA_UID")
                observed["env_name"] = os.getenv("IDEA_NAME")

            async def run(self):
                return None

        agent_module = types.ModuleType("aar.research_loop.agent")
        agent_module.AutonomousAgentLoop = Loop
        args = SimpleNamespace(
            idea_uid="smoke-uid",
            idea_name="single-node smoke",
            max_runtime=3600,
            max_iterations=1,
            model="claude-test",
            local=True,
        )
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}, clear=True),
            patch.dict(sys.modules, {"aar.research_loop.agent": agent_module}),
        ):
            launcher.cmd_agent(args, [])

        self.assertEqual(observed["env_uid"], "smoke-uid")
        self.assertEqual(observed["env_name"], "single-node smoke")
        self.assertEqual(observed["max_iterations"], 1)

    def test_max_iterations_caps_started_sessions_even_after_failure(self):
        sdk = types.ModuleType("claude_agent_sdk")
        for name in (
            "ClaudeSDKClient",
            "ClaudeAgentOptions",
            "AssistantMessage",
            "ResultMessage",
            "TextBlock",
            "ToolUseBlock",
        ):
            setattr(sdk, name, type(name, (), {}))
        server_tools = types.ModuleType("aar.research_loop.tools.server_api_tools")
        server_tools.create_server_api_tools_server = lambda: None
        prior_tools = types.ModuleType("aar.research_loop.tools.prior_work_tools")
        prior_tools.create_prior_work_tools_server = lambda: None
        findings = types.ModuleType("aar.research_loop.tools.findings_sync")
        findings.FindingsSync = type("FindingsSync", (), {})

        with patch.dict(
            sys.modules,
            {
                "claude_agent_sdk": sdk,
                "aar.research_loop.tools.server_api_tools": server_tools,
                "aar.research_loop.tools.prior_work_tools": prior_tools,
                "aar.research_loop.tools.findings_sync": findings,
            },
        ):
            agent_module = importlib.import_module("aar.research_loop.agent")
            AutonomousAgentLoop = agent_module.AutonomousAgentLoop

        class StopChecker:
            elapsed_time = 0.0

            @staticmethod
            def check():
                return None

            @staticmethod
            def record_error():
                return None

        loop = object.__new__(AutonomousAgentLoop)
        loop.local_mode = True
        loop.run_id = "agent-run"
        loop.idea_name = "smoke"
        loop.idea_uid = "smoke"
        loop.max_runtime_seconds = 3600
        loop.max_iterations = 1
        loop.findings_sync = None
        loop.session_count = 0
        loop.stop_checker = StopChecker()
        loop._run_session = AsyncMock(side_effect=RuntimeError("session failed"))

        with patch.object(agent_module.asyncio, "sleep", new=AsyncMock()):
            result = asyncio.run(loop.run())

        self.assertEqual(loop._run_session.await_count, 1)
        self.assertEqual(result["sessions"], 1)

    def test_put_model_stages_model_and_tokenizer_before_marker(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            _write_submission(source)
            with (
                patch.object(config, "HARNESS_TRANSPORT", "fs"),
                patch.object(config, "SUBMISSIONS_DIR", str(root / "submissions")),
            ):
                staged = Path(transport.put_model(str(source), "smoke-run"))

            self.assertTrue((staged / "model.safetensors").is_file())
            self.assertTrue((staged / "tokenizer.json").is_file())
            self.assertTrue((staged.parent / ".submitted").is_file())

    def test_put_model_rejects_missing_tokenizer_without_marker(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            _write_submission(source, tokenizer=False)
            submissions = root / "submissions"
            with (
                patch.object(config, "HARNESS_TRANSPORT", "fs"),
                patch.object(config, "SUBMISSIONS_DIR", str(submissions)),
            ):
                with self.assertRaisesRegex(ValueError, "tokenizer_config.json"):
                    transport.put_model(str(source), "smoke-run")

            self.assertFalse((submissions / "smoke-run" / ".submitted").exists())

    def test_saturated_held_out_is_still_detected_and_stripped(self):
        full = {
            "headline_pct": 0.0,
            "held_out_pct": {},
            "per_benchmark": {
                "visible": {"role": "safety", "mean": 0.5},
                "private": {"role": "held_out", "mean": 1.0, "inert": True},
            },
        }

        self.assertTrue(contains_held_out(full))
        visible = strip_held_out(full)
        self.assertNotIn("held_out_pct", visible)
        self.assertEqual(set(visible["per_benchmark"]), {"visible"})

    def test_eval_via_worker_false_submits_then_polls(self):
        with (
            patch.object(config, "EVAL_VIA_WORKER", False),
            patch.object(config, "HARNESS_TRANSPORT", "fs"),
            patch.object(eval_orchestration, "spawn_eval", return_value="slurm:42") as spawn,
            patch.object(
                eval_orchestration,
                "poll_scores",
                return_value={"headline_pct": 0.0},
            ) as poll,
        ):
            result = eval_orchestration.evaluate_model("smoke-run", "sycophancy")

        spawn.assert_called_once_with("smoke-run", "sycophancy")
        poll.assert_called_once_with("smoke-run")
        self.assertEqual(result["eval_launch"], "slurm:42")

    def test_sbatch_rejection_never_falls_back_to_inline_eval(self):
        failure = subprocess.CalledProcessError(1, ["sbatch"])
        with patch("subprocess.run", side_effect=failure), patch("subprocess.Popen") as popen:
            with self.assertRaises(subprocess.CalledProcessError):
                eval_orchestration._spawn_fs("smoke-run", "sycophancy")
        popen.assert_not_called()

    def test_method_template_defaults_to_configured_qwen(self):
        with patch.dict(os.environ, {"TARGET_MODEL": "Qwen/Qwen3.5-2B"}):
            self.assertEqual(MethodConfig().base_model, "Qwen/Qwen3.5-2B")
