"""Focused tests for the opt-in Kimi research-agent backend."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch

import requests

from aar.failure_feedback import FailureFeedbackError
from aar.research_loop.kimi_agent import (
    AutoDataActionResultValidationError,
    PROTECTED_SUBMISSION_FILES,
    KimiAgent,
    KimiToolUseBlock,
    OrchestrationIncident,
)
from aar.research_loop.kimi_write_guard import validate_tool_call
from aar.research_loop.tools.kimi_mcp_server import (
    SERVER_TOOLS,
    _text_content,
    create_server,
)
import run as launcher


class KimiAgentTest(unittest.TestCase):
    def test_autodata_sessions_receive_larger_bounded_continuation_budget(self) -> None:
        with patch.dict(os.environ, {"AAR_AUTODATA": "1"}, clear=True):
            agent = KimiAgent("test-agent", Path.cwd(), cli_path="/bin/true")
        self.assertEqual(agent.max_continuations, 96)

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

    def test_resumed_autodata_wait_precedes_first_model_call(self) -> None:
        run_id = "approved-run-1"
        workspace_id = "ws_" + "1" * 32
        execution_id = "exe_" + "2" * 32
        agent = KimiAgent(
            "test-agent",
            Path.cwd(),
            cli_path="/bin/true",
            completion_tool="share_finding",
        )
        run_command = AsyncMock()
        with (
            patch.dict(
                os.environ,
                {"AAR_AUTODATA": "1", "AAR_RESUME_APPROVED_PROPOSAL": "1"},
                clear=False,
            ),
            patch.object(
                agent, "_resume_approved_proposal_enabled", return_value=True
            ),
            patch.object(agent, "_approved_run_id", return_value=run_id),
            patch.object(agent, "_autodata_handoff_ready", return_value=False),
            patch.object(
                agent, "_autodata_workspace_id", return_value=workspace_id
            ),
            patch.object(
                agent,
                "_autodata_status_subject",
                return_value=execution_id,
            ),
            patch.object(agent, "_autodata_pending_action_record", return_value=None),
            patch.object(
                agent,
                "_autodata_native_status",
                return_value={
                    "execution_id": execution_id,
                    "status": "failed",
                    "phase": "meta_optimization",
                },
            ),
            patch.object(agent, "_run_command", new=run_command),
        ):
            result = asyncio.run(agent.execute("resume the approved proposal"))

        self.assertFalse(result.success)
        self.assertIn("terminated before handoff", result.error or "")
        run_command.assert_not_awaited()

    def test_resumed_autodata_idle_without_action_fails_within_short_sla(self) -> None:
        run_id = "approved-run-1"
        workspace_id = "ws_" + "1" * 32
        execution_id = "exe_" + "2" * 32
        agent = KimiAgent(
            "test-agent",
            Path.cwd(),
            cli_path="/bin/true",
            completion_tool="share_finding",
        )
        run_command = AsyncMock()
        with (
            patch.dict(
                os.environ,
                {
                    "AAR_AUTODATA": "1",
                    "AAR_RESUME_APPROVED_PROPOSAL": "1",
                    "AAR_AUTODATA_HOST_IDLE_GRACE_SECONDS": "0.000000001",
                },
                clear=False,
            ),
            patch.object(
                agent, "_resume_approved_proposal_enabled", return_value=True
            ),
            patch.object(agent, "_approved_run_id", return_value=run_id),
            patch.object(agent, "_autodata_handoff_ready", return_value=False),
            patch.object(
                agent, "_autodata_workspace_id", return_value=workspace_id
            ),
            patch.object(
                agent, "_autodata_status_subject", return_value=execution_id
            ),
            patch.object(agent, "_autodata_pending_action_record", return_value=None),
            patch.object(
                agent,
                "_require_fresh_autodata_supervisor_status",
                return_value={"state": "idle"},
            ),
            patch.object(
                agent,
                "_autodata_native_status",
                return_value={
                    "execution_id": execution_id,
                    "status": "active",
                },
            ),
            patch.object(agent, "_run_command", new=run_command),
            patch("aar.research_loop.kimi_agent.asyncio.sleep", new=AsyncMock()),
        ):
            result = asyncio.run(agent.execute("resume the approved proposal"))

        self.assertFalse(result.success)
        self.assertEqual(
            result.failure["error_code"], "autodata_supervisor_idle_stall"
        )
        run_command.assert_not_awaited()

    def test_required_completion_resumes_after_bounded_turn_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys, time\n"
                "from pathlib import Path\n"
                "counter = Path(os.environ['KIMI_CODE_HOME']) / 'timeout-calls'\n"
                "call = int(counter.read_text()) + 1 if counter.exists() else 1\n"
                "counter.write_text(str(call))\n"
                "if call == 1:\n"
                "  time.sleep(30)\n"
                "else:\n"
                "  assert '--continue' in sys.argv\n"
                "  print(json.dumps({'role': 'assistant', 'content': 'recovered', "
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
                    max_continuations=2,
                    turn_timeout_seconds=0.2,
                ).execute("complete the task")
            )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output["continuations"], 1)
        self.assertEqual(result.output["result_message"], "recovered")

    def test_stalled_checkpoint_retries_do_not_consume_continuation_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "counter = Path(os.environ['KIMI_CODE_HOME']) / 'checkpoint-calls'\n"
                "call = int(counter.read_text()) + 1 if counter.exists() else 1\n"
                "counter.write_text(str(call))\n"
                "if call == 1:\n"
                "  print(json.dumps({'role': 'assistant', 'content': 'starting'}))\n"
                "elif call == 2:\n"
                "  assert '--continue' in sys.argv\n"
                "  print(json.dumps({'role': 'assistant', 'content': 'The'}))\n"
                "else:\n"
                "  assert '--continue' in sys.argv\n"
                "  print(json.dumps({'role': 'assistant', 'content': 'done', "
                "'tool_calls': [{'function': {'name': 'finish', "
                "'arguments': '{}'}}]}))\n"
            )
            cli.chmod(0o755)
            result = asyncio.run(
                KimiAgent(
                    "test-agent",
                    root,
                    cli_path=str(cli),
                    completion_tool="finish",
                    max_continuations=1,
                    max_checkpoint_retries=1,
                ).execute("complete the task")
            )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output["continuations"], 1)
        self.assertEqual(result.output["result_message"], "done")

    def test_stalled_checkpoint_retries_remain_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json\n"
                "print(json.dumps({'role': 'assistant', 'content': 'The'}))\n"
            )
            cli.chmod(0o755)
            result = asyncio.run(
                KimiAgent(
                    "test-agent",
                    root,
                    cli_path=str(cli),
                    completion_tool="finish",
                    max_continuations=1,
                    max_checkpoint_retries=1,
                ).execute("complete the task")
            )

        self.assertFalse(result.success)
        self.assertIn("repeatedly stopped", result.error or "")
        self.assertIn("checkpoint tool finish", result.error or "")

    def test_completion_exhaustion_is_retryable_session_advance_when_enabled(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json\n"
                "print(json.dumps({'role': 'assistant', 'content': 'working', "
                "'tool_calls': [{'function': {'name': 'Bash', "
                "'arguments': '{\"command\": \"true\"}'}}]}))\n"
            )
            cli.chmod(0o755)
            with patch.dict(
                os.environ,
                {"AAR_KIMI_CONTINUATION_EXHAUSTION_RETRYABLE": "1"},
                clear=False,
            ):
                result = asyncio.run(
                    KimiAgent(
                        "test-agent",
                        root,
                        cli_path=str(cli),
                        completion_tool="finish",
                        max_continuations=1,
                    ).execute("complete the task")
                )

        self.assertFalse(result.success)
        self.assertEqual(result.failure["error_code"], "required_completion_missing")
        self.assertTrue(result.failure["retryable"])
        self.assertEqual(result.failure["disposition"], "advance_session")

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
                        "execution_ready": True,
                        "journaled": True,
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
                "execution_ready": True,
                "journaled": True,
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

    def test_slurm_timeout_repairs_malformed_marker_instead_of_waiting_forever(
        self,
    ) -> None:
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
                "execution_ready": True,
                "journaled": True,
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
            (scores / f"{run_id}.failed.json").write_text(
                '{"status":"failed","error":"private malformed body"}'
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
                patch(
                    "aar.research_loop.kimi_agent._method_code",
                    return_value=("method code", "abc123"),
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
            self.assertNotIn("log_path", failure)

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
                "execution_ready": True,
                "journaled": True,
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
                "error": "held-out row; API_KEY=must-not-leak",
                "retryable": False,
                "log_path": str(
                    root / "secrets" / "failure-evidence" / "train-123.out"
                ),
            }
            evidence = root / "secrets" / "failure-evidence"
            evidence.mkdir(parents=True)
            (evidence / "train-123.out").write_text("operator evidence")
            (scores / f"{run_id}.failed.json").write_text(json.dumps(failure))
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")

            with patch.dict(
                os.environ,
                {
                    "SCORES_DIR": str(scores),
                    "TEAM_DIR": str(root),
                    "IDEA_UID": idea_uid,
                },
                clear=False,
            ), patch(
                "aar.research_loop.kimi_agent._method_code",
                return_value=("method code", "abc123"),
            ):
                prompt = agent._with_previous_failure_feedback("do research")
                self.assertIn("AUTOMATIC HELD-OUT-SAFE FAILURE FEEDBACK", prompt)
                self.assertIn("training_python_exception", prompt)
                self.assertNotIn("held-out row", prompt)
                self.assertNotIn("must-not-leak", prompt)
                self.assertNotIn("train-123.out", prompt)
                self.assertNotIn('"evidence":', prompt)

                (scores / f"{run_id}.json").write_text("{}\n")
                self.assertEqual(
                    agent._with_previous_failure_feedback("do research"),
                    "do research",
                )

    def test_previous_failure_rejects_unbound_or_invalid_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scores = root / "scores"
            proposals = scores / ".proposals"
            runs = proposals / "runs"
            runs.mkdir(parents=True)
            idea_uid = "kimi-invalid-feedback"
            run_id = f"{idea_uid}-candidate-1"
            marker = {
                "approved": True,
                "execution_ready": True,
                "journaled": True,
                "idea_name": "kimi_candidate",
                "code_hash": "abc123",
            }
            (proposals / f"{idea_uid}.json").write_text(json.dumps(marker))
            (runs / "candidate.json").write_text(
                json.dumps({**marker, "run_id": run_id, "stamped_ts": 1})
            )
            (scores / f"{run_id}.failed.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "status": "failed",
                        "run_id": "different-run",
                        "stage": "training",
                        "error_code": "training_failed",
                        "retryable": False,
                        "error": "held-out prompt row",
                        "log_path": "/outside/operator.log",
                    }
                )
            )

            agent = KimiAgent("test-agent", root, cli_path="/bin/true")
            with patch.dict(
                os.environ,
                {
                    "SCORES_DIR": str(scores),
                    "TEAM_DIR": str(root),
                    "IDEA_UID": idea_uid,
                },
                clear=False,
            ):
                assert agent._with_previous_failure_feedback("do research") == (
                    "do research"
                )

    def test_training_failure_feedback_classifies_empty_preference_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scores = root / "scores"
            proposals = scores / ".proposals"
            runs = proposals / "runs"
            runs.mkdir(parents=True)
            idea_uid = "kimi-empty-data"
            run_id = f"{idea_uid}-candidate-1"
            marker = {
                "approved": True,
                "execution_ready": True,
                "journaled": True,
                "idea_name": "kimi_candidate",
                "code_hash": "abc123",
                "run_id": run_id,
                "paper": {},
            }
            (proposals / f"{idea_uid}.json").write_text(json.dumps(marker))
            (runs / f"{run_id}.json").write_text(json.dumps(marker))
            (scores / f"{run_id}.failed.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "status": "failed",
                        "run_id": run_id,
                        "stage": "training",
                        "error_code": "training_python_exception",
                        "retryable": False,
                        "reason": "generated zero valid examples after filtering",
                    }
                )
            )
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")

            with patch.dict(
                os.environ,
                {
                    "SCORES_DIR": str(scores),
                    "TEAM_DIR": str(root),
                    "IDEA_UID": idea_uid,
                },
                clear=False,
            ), patch(
                "aar.research_loop.kimi_agent._method_code",
                return_value=("method code", "abc123"),
            ):
                prompt = agent._with_previous_failure_feedback("do research")

        self.assertIn("training_dataset_empty", prompt)
        self.assertIn("chosen and rejected fields", prompt)

    def test_training_failure_feedback_includes_known_sanitized_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scores = root / "scores"
            proposals = scores / ".proposals"
            runs = proposals / "runs"
            runs.mkdir(parents=True)
            idea_uid = "kimi-dataset-interface"
            run_id = f"{idea_uid}-candidate-1"
            marker = {
                "approved": True,
                "execution_ready": True,
                "journaled": True,
                "idea_name": "kimi_candidate",
                "code_hash": "abc123",
                "run_id": run_id,
                "paper": {},
            }
            (proposals / f"{idea_uid}.json").write_text(json.dumps(marker))
            (runs / f"{run_id}.json").write_text(json.dumps(marker))
            (scores / f"{run_id}.failed.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "status": "failed",
                        "run_id": run_id,
                        "stage": "training",
                        "error_code": "training_python_exception",
                        "retryable": False,
                        "reason": (
                            "AttributeError: 'list' object has no attribute 'map'; "
                            "API_KEY=must-not-leak"
                        ),
                    }
                )
            )
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")

            with patch.dict(
                os.environ,
                {
                    "SCORES_DIR": str(scores),
                    "TEAM_DIR": str(root),
                    "IDEA_UID": idea_uid,
                },
                clear=False,
            ), patch(
                "aar.research_loop.kimi_agent._method_code",
                return_value=("method code", "abc123"),
            ):
                prompt = agent._with_previous_failure_feedback("do research")

        self.assertIn("training_dataset_interface_invalid", prompt)
        self.assertIn("'list' object has no attribute 'map'", prompt)
        self.assertIn("datasets.Dataset", prompt)
        self.assertNotIn("must-not-leak", prompt)
        self.assertIn("[REDACTED]", prompt)

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
            self.assertFalse(observed["config_is_link"])
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
            self.assertIn('event = "PreToolUse"', observed["config"])
            self.assertIn('matcher = "^(Write|Edit)$"', observed["config"])
            self.assertIn("aar.research_loop.kimi_write_guard", observed["config"])
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

    def test_forced_finding_tool_requires_bound_run_and_writeup_together(self) -> None:
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
        run_id = "approved-chain-run-1"
        try:
            with agent._request_policy_proxy(env) as controller:
                controller.arm(
                    "share_finding",
                    argument_schema={
                        "run_id": {"type": "string", "const": run_id},
                        "results_writeup": {"type": "string", "minLength": 80},
                    },
                )
                request = {
                    "model": "Kimi-K2.6",
                    "tools": [
                        {"type": "function", "function": {"name": "Read"}},
                        {
                            "type": "function",
                            "function": {
                                "name": "mcp__server-api-tools__share_finding",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "summary": {"type": "string"},
                                        "run_id": {"type": "string"},
                                        "results_writeup": {"type": "string"},
                                    },
                                    "required": ["summary"],
                                },
                            },
                        },
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
        self.assertEqual(len(observed[0]["tools"]), 1)
        parameters = observed[0]["tools"][0]["function"]["parameters"]
        self.assertEqual(
            parameters["required"],
            ["summary", "run_id", "results_writeup"],
        )
        self.assertEqual(parameters["properties"]["run_id"]["const"], run_id)
        self.assertEqual(
            parameters["properties"]["results_writeup"]["minLength"], 80
        )
        self.assertNotIn("tool_choice", observed[1])
        self.assertEqual(len(observed[1]["tools"]), 2)

    def test_completion_only_mode_forces_bound_finding_on_first_request(self) -> None:
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
        run_id = "approved-chain-run-1"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json, os, urllib.request\n"
                "url = os.environ['KIMI_MODEL_BASE_URL'].rstrip('/') + "
                "'/chat/completions'\n"
                "payload = {'model': 'Kimi-K2.6', 'tools': [\n"
                "  {'type': 'function', 'function': {'name': 'Read'}},\n"
                "  {'type': 'function', 'function': {\n"
                "    'name': 'mcp__server-api-tools__get_literature',\n"
                "    'parameters': {'type': 'object', 'properties': {}}}},\n"
                "  {'type': 'function', 'function': {\n"
                "    'name': 'mcp__server-api-tools__share_finding',\n"
                "    'parameters': {'type': 'object', 'properties': {\n"
                "      'summary': {'type': 'string'},\n"
                "      'run_id': {'type': 'string'},\n"
                "      'results_writeup': {'type': 'string'}},\n"
                "      'required': ['summary']}}}]}\n"
                "request = urllib.request.Request(url, "
                "data=json.dumps(payload).encode(), "
                "headers={'Content-Type': 'application/json'}, method='POST')\n"
                "with urllib.request.urlopen(request, timeout=5) as response:\n"
                "  response.read()\n"
                "arguments = {'summary': 'done', "
                f"'run_id': {run_id!r}, "
                "'results_writeup': 'The public benchmark was unchanged, capability "
                "behavior remained stable, the likely mechanism was limited, and the "
                "two-item canary is too small for scientific conclusions.'}\n"
                "print(json.dumps({'role': 'assistant', 'content': 'done', "
                "'tool_calls': [{'function': {'name': "
                "'mcp__server-api-tools__share_finding', "
                "'arguments': json.dumps(arguments)}}]}))\n"
            )
            cli.chmod(0o755)
            agent = KimiAgent(
                "test-agent",
                root,
                cli_path=str(cli),
                completion_tool="share_finding",
                force_completion_tool_first_turn=True,
            )
            try:
                with (
                    patch.dict(
                        os.environ,
                        {
                            "KIMI_MODEL_BASE_URL": (
                                f"http://127.0.0.1:{upstream.server_port}/v1"
                            ),
                            "KIMI_MODEL_API_KEY": "secret",
                            "AAR_REQUIRE_SUCCESSFUL_ITERATIONS": "0",
                        },
                        clear=False,
                    ),
                    patch.object(agent, "_approved_run_id", return_value=run_id),
                ):
                    result = asyncio.run(agent.execute("publish only"))
            finally:
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

        self.assertTrue(result.success, result.error)
        self.assertEqual(len(observed), 1)
        request = observed[0]
        self.assertEqual(request["tool_choice"], "required")
        self.assertEqual(len(request["tools"]), 1)
        function = request["tools"][0]["function"]
        self.assertTrue(function["name"].endswith("__share_finding"))
        parameters = function["parameters"]
        self.assertEqual(
            parameters["required"],
            ["summary", "run_id", "results_writeup"],
        )
        self.assertEqual(parameters["properties"]["run_id"]["const"], run_id)
        self.assertEqual(
            parameters["properties"]["results_writeup"]["minLength"], 80
        )

    def test_nonzero_cli_exit_is_a_failed_agent_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cli = root / "kimi"
            cli.write_text(f"#!{sys.executable}\nimport sys\nsys.stderr.write('bad auth')\nsys.exit(7)\n")
            cli.chmod(0o755)
            with patch.dict(os.environ, {"TEAM_DIR": str(root)}, clear=False):
                result = asyncio.run(
                    KimiAgent("test-agent", root, cli_path=str(cli)).execute("task")
                )
            self.assertFalse(result.success)
            self.assertIn("status 7", result.error or "")
            self.assertNotIn("bad auth", result.error or "")
            self.assertEqual(result.failure["error_code"], "kimi_cli_failed")
            self.assertNotIn("evidence", result.failure)

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

    def test_incomplete_finding_calls_force_one_exact_bound_retry(self) -> None:
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
                },
                {
                    "tool": "mcp__server-api-tools__share_finding",
                    "input": {
                        "results_writeup": "A sufficiently detailed result discussion "
                        "that was incorrectly sent without the approved run binding."
                    },
                },
            ]
        }
        with (
            patch.object(agent, "_approved_run_id", return_value=run_id),
            patch.object(agent, "_resume_approved_proposal_enabled", return_value=True),
            patch.object(agent, "_current_training_job_id", return_value="12345"),
        ):
            prompt = agent._continuation_prompt(output)
            schema = agent._checkpoint_argument_schema(
                agent._continuation_tool(output)
            )

        self.assertIn("did not persist", prompt)
        self.assertIn("SAME structured call", prompt)
        self.assertIn(f'run_id="{run_id}" exactly', prompt)
        self.assertEqual(
            schema,
            {
                "run_id": {"type": "string", "const": run_id},
                "results_writeup": {"type": "string", "minLength": 80},
            },
        )

    def test_deterministic_checkpoint_arguments_are_schema_bound(self) -> None:
        agent = KimiAgent("test-agent", Path.cwd(), cli_path="/bin/true")

        self.assertEqual(
            agent._checkpoint_argument_schema(
                "Read", prompt='Call Read exactly once with path="/tmp/input.json".'
            ),
            {"path": {"type": "string", "const": "/tmp/input.json"}},
        )
        self.assertEqual(
            agent._checkpoint_argument_schema(
                "Bash", prompt='Call Bash exactly once with command="python check.py".'
            ),
            {"command": {"type": "string", "const": "python check.py"}},
        )
        self.assertEqual(
            agent._checkpoint_argument_schema(
                "Write", prompt='Call Write exactly once with path="/tmp/run.py".'
            ),
            {"path": {"type": "string", "const": "/tmp/run.py"}},
        )

    def test_host_validator_signal_failure_becomes_targeted_write_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ideas = root / "methods"
            method = ideas / "chain__kimi_candidate" / "run.py"
            method.parent.mkdir(parents=True)
            method.write_text("def run_experiment(config):\n    return {}\n")
            agent = KimiAgent(
                "test-agent",
                root,
                cli_path="/bin/true",
                completion_tool="share_finding",
            )
            output = {"tool_uses": []}
            validation_prompt = (
                "Call Bash to validate the complete import, MethodConfig, dry-run "
                "contract before proposal submission."
            )

            with (
                patch.dict(
                    os.environ,
                    {
                        "AAR_IDEAS_DIR": str(ideas),
                        "IDEA_NAME": "chain",
                    },
                    clear=False,
                ),
                patch(
                    "aar.research_loop.kimi_agent.subprocess.run",
                    return_value=subprocess.CompletedProcess(
                        args=["validator"],
                        returncode=-9,
                        stdout="",
                        stderr="",
                    ),
                ),
            ):
                self.assertTrue(
                    agent._execute_host_checkpoint(validation_prompt, output)
                )
                proof = json.loads(
                    (method.parent / ".aar-method-contract.json").read_text()
                )
                next_prompt = agent._continuation_prompt(output)

            self.assertEqual(proof["status"], "failed")
            self.assertIn("SIGKILL", proof["errors"][0])
            self.assertIn("config.dry_run", proof["errors"][0])
            self.assertIn("Write tool exactly once", next_prompt)
            self.assertIn("config.dry_run", next_prompt)
            self.assertEqual(output["tool_uses"][0]["input"]["return_code"], -9)

    def test_fresh_session_repairs_existing_failed_candidate_from_exact_errors(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ideas = root / "methods"
            method = ideas / "chain__kimi_candidate" / "run.py"
            method.parent.mkdir(parents=True)
            method.write_text("from aar.phase_timing import phase_timing\n")
            proof = method.parent / ".aar-method-contract.json"
            contract_error = (
                "missing required phase contexts: training; use exactly "
                "`from aar.phase_timing import phase` and "
                "`with phase(\"<required_name>\"):`; unsupported phase context "
                "callable(s) found: phase_timing"
            )
            proof.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "source_sha256": hashlib.sha256(method.read_bytes()).hexdigest(),
                        "errors": [contract_error],
                    }
                )
            )
            agent = KimiAgent(
                "test-agent",
                Path.cwd(),
                cli_path="/bin/true",
                completion_tool="share_finding",
            )

            with patch.dict(
                os.environ,
                {
                    "AAR_IDEAS_DIR": str(ideas),
                    "IDEA_NAME": "chain",
                },
                clear=False,
            ):
                prompt = agent._continuation_prompt({"tool_uses": []})

            self.assertIn("Write tool exactly once", prompt)
            self.assertIn("from aar.phase_timing import phase", prompt)
            self.assertIn("phase_timing", prompt)
            self.assertNotIn("candidate scaffold", prompt)

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

            with patch.object(
                agent,
                "_continuation_prompt",
                return_value=(
                    "Call the native structured MCP tool review_autodata_action "
                    "exactly once now with action_id=act_" + "1" * 24
                ),
            ):
                self.assertEqual(
                    agent._continuation_tool(empty_output),
                    "review_autodata_action",
                )
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
            ), patch(
                "aar.research_loop.kimi_agent._method_code",
                return_value=("method code", "hash-1"),
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
                            "execution_ready": True,
                            "journaled": True,
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
            self.assertIn("head -n 10000", recipe_prompt)
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

    def test_continuation_checkpoint_reuses_computed_prompt(self) -> None:
        agent = KimiAgent(
            "test-agent",
            Path.cwd(),
            cli_path="/bin/true",
            completion_tool="share_finding",
        )
        output = {"tool_uses": []}
        prompt = "Call the native Read tool exactly once now"
        with patch.object(agent, "_continuation_prompt") as recompute:
            self.assertEqual(
                agent._continuation_tool(output, prompt=prompt), "Read"
            )
        recompute.assert_not_called()

    def test_approved_training_submission_is_adapter_controlled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal_dir = root / "scores" / ".proposals"
            runs = proposal_dir / "runs"
            runs.mkdir(parents=True)
            marker = {
                "approved": True,
                "execution_ready": True,
                "journaled": True,
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
                patch.object(agent, "_validate_protected_submission_files"),
                patch(
                    "aar.research_loop.kimi_agent._method_code",
                    return_value=("method code", "hash-1"),
                ),
                patch("aar.research_loop.kimi_agent.subprocess.run", side_effect=submit),
            ):
                agent._ensure_approved_training_submission()

            self.assertEqual(receipt.read_text(), f"run_id={run_id}\njob_id=12345\n")

    def test_post_approval_method_mutation_prevents_host_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ideas = root / "ideas"
            idea_name = "chain__kimi_candidate"
            method_dir = ideas / idea_name
            method_dir.mkdir(parents=True)
            (method_dir / "run.py").write_text("from .helper import VALUE\n")
            helper = method_dir / "helper.py"
            helper.write_text("VALUE = 1\n")

            scores = root / "scores"
            proposal_dir = scores / ".proposals"
            runs = proposal_dir / "runs"
            runs.mkdir(parents=True)
            idea_uid = "chain-uid"
            run_id = f"{idea_uid}-{idea_name}-1"
            environment = {
                "AAR_AUTODATA": "0",
                "AAR_REQUIRE_TRAIN_RECEIPT": "1",
                "SCORES_DIR": str(scores),
                "TEAM_DIR": str(root / "team"),
                "IDEA_UID": idea_uid,
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch("aar.config.IDEAS_DIR", str(ideas)),
                patch("aar.config.SEED_IDEAS_DIR", str(root / "seed-ideas")),
            ):
                from aar.research_loop.tools.server_api_tools import _method_code

                _, code_hash = _method_code(idea_name)
                marker = {
                    "approved": True,
                    "execution_ready": True,
                    "journaled": True,
                    "idea_name": idea_name,
                    "code_hash": code_hash,
                    "run_id": run_id,
                    "paper": {},
                }
                (proposal_dir / f"{idea_uid}.json").write_text(json.dumps(marker))
                (runs / f"{run_id}.json").write_text(
                    json.dumps({**marker, "stamped_ts": 1})
                )
                agent = KimiAgent(
                    "test-agent",
                    root,
                    cli_path="/bin/true",
                    completion_tool="share_finding",
                )
                self.assertEqual(agent._approved_run_id(), run_id)

                helper.write_text("VALUE = 2\n")
                with (
                    patch.object(agent, "_validate_protected_submission_files"),
                    patch("aar.research_loop.kimi_agent.subprocess.run") as submit,
                ):
                    agent._ensure_approved_training_submission()

                self.assertIsNone(agent._approved_run_id())
                submit.assert_not_called()

    def test_production_only_canary_verifies_rows_and_writes_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            team = Path(temp) / "team"
            run_id = "chain-uid-candidate-1"
            run_root = team / "autodata" / run_id
            run_root.mkdir(parents=True)
            verification = {
                "schema": "aar.autodata.lifecycle-verification/v1",
                "run_id": run_id,
                "available_rows": 1000,
                "timing": {
                    "schema": "aar.autodata.lifecycle-timing/v1",
                    "run_id": run_id,
                },
            }
            with (
                patch.dict(
                    os.environ,
                    {
                        "TEAM_DIR": str(team),
                        "AAR_AUTODATA_STOP_AFTER": "production",
                        "AAR_AUTODATA_PRODUCTION_ROWS": "1000",
                    },
                    clear=False,
                ),
                patch(
                    "aar.infrastructure.autodata_lifecycle.verify_preflight",
                    return_value=verification,
                ),
            ):
                marker = KimiAgent._complete_autodata_production_canary(run_id)

            value = json.loads(marker.read_text())
            self.assertEqual(
                value["schema"], "aar.autodata.production-canary-complete/v1"
            )
            self.assertEqual(value["required_accepted_rows"], 1000)
            self.assertEqual(value["verification"], verification)
            timing_path = run_root / "autodata-lifecycle-timing.json"
            self.assertEqual(value["timing_report"], str(timing_path))
            self.assertEqual(json.loads(timing_path.read_text()), verification["timing"])
            self.assertFalse((team / ".train_submissions").exists())

    def test_training_smoke_canary_proves_consumption_and_one_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            team = Path(temp) / "team"
            run_id = "chain-uid-candidate-1"
            run_root = team / "autodata" / run_id
            run_root.mkdir(parents=True)
            model_path = team / "_train" / run_id
            model_path.mkdir(parents=True)
            weight = model_path / "adapter_model.safetensors"
            weight.write_bytes(b"adapter")
            receipt = run_root / "training-consumption.json"
            receipt.write_text("{}")
            phase_timings = team / "timings" / f"{run_id}.research.jsonl"
            phase_timings.parent.mkdir()
            phase_timings.write_text('{"phase":"training"}\n')
            job_id = "12345"
            submission = team / ".train_submissions" / f"{run_id}.env"
            submission.parent.mkdir()
            submission.write_text(f"run_id={run_id}\njob_id={job_id}\n")
            verification = {
                "schema": "aar.autodata.lifecycle-verification/v1",
                "run_id": run_id,
                "available_rows": 1000,
                "required_rows": 1000,
                "dataset_sha256": "sha256:dataset",
                "production_execution_id": "exe_production",
                "timing": {
                    "schema": "aar.autodata.lifecycle-timing/v1",
                    "run_id": run_id,
                },
            }
            smoke_dir = team / "method_smoke"
            smoke_dir.mkdir()
            (smoke_dir / f"{run_id}.passed.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "passed",
                        "run_id": run_id,
                        "model_path": str(model_path),
                        "adapter_weight_file": weight.name,
                        "smoke_run": True,
                        "optimizer_steps": 1,
                        "slurm_job_id": job_id,
                        "phase_timings": str(phase_timings),
                        "autodata_consumption": {
                            **verification,
                            "consumed_rows": 1000,
                            "consumption_receipt": str(receipt),
                        },
                    }
                )
            )
            with (
                patch.dict(
                    os.environ,
                    {
                        "TEAM_DIR": str(team),
                        "AAR_AUTODATA_STOP_AFTER": "training_smoke",
                        "AAR_AUTODATA_PRODUCTION_ROWS": "1000",
                    },
                    clear=False,
                ),
                patch(
                    "aar.infrastructure.autodata_lifecycle.verify_preflight",
                    return_value=verification,
                ),
            ):
                marker = KimiAgent._complete_autodata_training_smoke_canary(run_id)

            value = json.loads(marker.read_text())
            self.assertEqual(
                value["schema"],
                "aar.autodata.training-smoke-canary-complete/v1",
            )
            self.assertEqual(value["training"]["consumed_rows"], 1000)
            self.assertEqual(value["training"]["optimizer_steps"], 1)
            self.assertEqual(
                value["training"]["adapter_weight_sha256"],
                hashlib.sha256(b"adapter").hexdigest(),
            )

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
                "execution_ready": True,
                "journaled": True,
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
                patch.object(agent, "_validate_protected_submission_files"),
                patch(
                    "aar.research_loop.kimi_agent._method_code",
                    return_value=("method code", "hash-1"),
                ),
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
                digest = "sha256:" + hashlib.sha256(handoff.read_bytes()).hexdigest()
                (handoff.parent / "training-handoff.verified.json").write_text(
                    json.dumps(
                        {
                            "schema": "aar.autodata.training-handoff-verified/v1",
                            "run_id": run_id,
                            "training_handoff_sha256": digest,
                            "meta_execution_id": "exe_" + "1" * 32,
                            "production_execution_id": "exe_" + "2" * 32,
                        }
                    )
                )
                agent._ensure_approved_training_submission()
                run.assert_called_once()

            self.assertEqual(receipt.read_text(), f"run_id={run_id}\njob_id=12345\n")

    def test_autodata_handoff_integrity_errors_fail_instead_of_waiting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            team = Path(temporary) / "team"
            run_id = "run-one"
            run_root = team / "autodata" / run_id
            run_root.mkdir(parents=True)
            environment = {
                "TEAM_DIR": str(team),
                "AAR_AUTODATA_HANDOFF_PUBLICATION_GRACE_SECONDS": "0",
            }
            with patch.dict(os.environ, environment, clear=False):
                self.assertFalse(KimiAgent._autodata_handoff_ready(run_id))
                (run_root / "training-handoff.json").write_text("{}\n")
                with self.assertRaises(FailureFeedbackError) as partial:
                    KimiAgent._autodata_handoff_ready(run_id)
                self.assertEqual(
                    partial.exception.feedback["error_code"],
                    "autodata_handoff_publication_incomplete",
                )
                (run_root / "training-handoff.verified.json").write_text("not json")
                with self.assertRaises(FailureFeedbackError) as malformed:
                    KimiAgent._autodata_handoff_ready(run_id)
                self.assertEqual(
                    malformed.exception.feedback["error_code"],
                    "autodata_handoff_marker_invalid",
                )

    def test_autodata_rejects_proof_created_without_required_loader_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            method = Path(temp) / "run.py"
            method.write_text("method code\n")
            proof = method.parent / ".aar-method-contract.json"
            proof.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "source_sha256": hashlib.sha256(method.read_bytes()).hexdigest(),
                        "requirements": {
                            "run_dry_run": True,
                            "require_gemma4_targets": True,
                            "require_smoke_run": True,
                            "require_autodata_loader": False,
                        },
                        "errors": [],
                    }
                )
            )
            with patch.dict(os.environ, {"AAR_AUTODATA": "1"}, clear=False):
                status, errors = KimiAgent._method_contract_status(method)

            self.assertEqual(status, "failed")
            self.assertIn("require_autodata_loader", errors[0])
            self.assertIn("without removing flags", errors[0])

    def test_autodata_continuation_resumes_approved_run_before_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal_dir = root / ".proposals"
            runs = proposal_dir / "runs"
            runs.mkdir(parents=True)
            run_id = "chain-uid-chain__kimi_candidate-1"
            marker = {
                "approved": True,
                "execution_ready": True,
                "journaled": True,
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
            state = root / "state.db"
            action_id = "act_" + "2" * 24
            action_spec = {
                "id": action_id,
                "kind": "clarify_design",
                "scope": {"kind": "workspace", "id": "ws_" + "1" * 32},
                "instructions": "Confirm the reviewed workspace intent.",
                "allowed_paths": ["autodata.workspace.json"],
                "editable_root": str(root / "draft"),
                "outputs": ["summary", "decisions"],
            }
            draft = root / "draft"
            draft.mkdir()
            (draft / "autodata.workspace.json").write_text(
                json.dumps(
                    {
                        "schema": "autodata.workspace/v1",
                        "name": "compiled-workspace",
                        "execution_defaults": {"concurrency": 8},
                    }
                )
            )
            with sqlite3.connect(state) as connection:
                connection.execute(
                    "CREATE TABLE actions("
                    "id TEXT,kind TEXT,status TEXT,specJson TEXT,createdAt TEXT)"
                )
            control = root / "lifecycle-control.json"
            control.write_text(
                json.dumps(
                    {
                        "schema": "aar.autodata.lifecycle-control/v1",
                        "subjects": [],
                    }
                )
            )
            with patch.dict(
                os.environ,
                {
                    "AAR_AUTODATA": "1",
                    "AAR_IDEAS_DIR": str(root / "methods"),
                    "IDEA_NAME": "chain",
                    "IDEA_UID": "chain-uid",
                    "SCORES_DIR": str(root),
                    "TEAM_DIR": str(root / "team"),
                    "AAR_AUTODATA_STATE": str(state),
                    "AAR_AUTODATA_SUPERVISOR_CONTROL": str(control),
                },
                clear=False,
            ), patch(
                "aar.research_loop.kimi_agent._method_code",
                return_value=("method code", "hash-1"),
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
                control.write_text(
                    json.dumps(
                        {
                            "schema": "aar.autodata.lifecycle-control/v1",
                            "subjects": [
                                {
                                    "kind": "workspace",
                                    "subject_id": workspace_id,
                                    "status": "registered",
                                }
                            ],
                        }
                    )
                )
                with patch.object(
                    KimiAgent,
                    "_autodata_native_status",
                    return_value={
                        "workspace": {"id": workspace_id, "status": "active"}
                    },
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "deterministic waits must be handled without Kimi"
                    ):
                        agent._continuation_prompt(output)
                self.assertTrue(agent._autodata_wait_required(output))

                with sqlite3.connect(state) as connection:
                    connection.execute(
                        "INSERT INTO actions VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
                        (
                            action_id,
                            "clarify_design",
                            "in_progress",
                            json.dumps(action_spec),
                        ),
                    )
                lease_path = agent._autodata_action_lease_path(action_id)
                agent._write_private_text(lease_path, "x" * 32)
                result_path = agent._autodata_action_result_path(action_id)
                result_path.unlink(missing_ok=True)
                try:
                    action_prompt = agent._continuation_prompt(output)
                    self.assertIn("securely leased", action_prompt)
                    self.assertIn(str(result_path), action_prompt)
                    self.assertIn("Confirm the reviewed workspace intent", action_prompt)
                    self.assertIn("preserve every existing key", action_prompt)
                    self.assertIn('\\"execution_defaults\\"', action_prompt)
                    self.assertIn('\\"concurrency\\": 8', action_prompt)
                    self.assertEqual(agent._continuation_tool(output), "Write")

                    result_path.write_text(
                        json.dumps({"summary": "confirmed", "decisions": []})
                    )
                    with (
                        patch.object(
                            KimiAgent,
                            "_autodata_cli",
                            return_value={"status": "completed"},
                        ) as cli,
                        patch.object(
                            KimiAgent,
                            "_autodata_native_status",
                            return_value={"status": "active"},
                        ),
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "deterministic waits must be handled without Kimi",
                        ):
                            agent._continuation_prompt(output)
                    cli.assert_called_once_with(
                        "action",
                        "complete",
                        action_id,
                        "--lease-token=" + "x" * 32,
                        "--result",
                        str(result_path),
                    )
                    self.assertFalse(lease_path.exists())
                    self.assertFalse(result_path.exists())
                finally:
                    lease_path.unlink(missing_ok=True)
                    result_path.unlink(missing_ok=True)

                grounding_action = {
                    "spec": {
                        "editable_root": str(draft),
                        "allowed_paths": ["grounding/**"],
                    }
                }
                agent._autodata_prepare_editable_paths(grounding_action)
                self.assertTrue((draft / "grounding").is_dir())

                recipe = root / "reviewed-recipe"
                reviewed_grounding = recipe / "grounding"
                reviewed_grounding.mkdir(parents=True)
                (reviewed_grounding / "coverage.json").write_text("{}")
                (reviewed_grounding / "build_manifest.py").write_text(
                    """import argparse, json
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--count', type=int, required=True)
p.add_argument('--coverage')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.write_text(json.dumps({'schema': 'autodata.grounding/v1', 'tasks': [{'id': f'task-{i}'} for i in range(a.count)]}))
"""
                )
                manifest = draft / "grounding" / "manifest.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "schema": "autodata.grounding/v1",
                            "sources": [{"name": "incomplete"}],
                        }
                    )
                )
                grounding_action["kind"] = "author_grounding"
                with patch.dict(
                    os.environ,
                    {
                        "AAR_AUTODATA_RECIPE_ROOT": str(recipe),
                        "AAR_AUTODATA_TUNING_TASKS": "2",
                        "AAR_AUTODATA_VALIDATION_TASKS": "1",
                        "AAR_AUTODATA_TEST_TASKS": "1",
                    },
                    clear=False,
                ):
                    agent._autodata_repair_incomplete_grounding(grounding_action)
                repaired = json.loads(manifest.read_text())
                self.assertEqual(len(repaired["tasks"]), 4)
                editable_context = json.loads(
                    agent._autodata_editable_context(grounding_action)
                )
                self.assertIn("grounding/manifest.json", editable_context)
                self.assertIn('"tasks"', editable_context["grounding/manifest.json"])

                execution_id = "exe_" + "3" * 32
                with sqlite3.connect(state) as connection:
                    connection.execute(
                        "CREATE TABLE executions("
                        "id TEXT,status TEXT,workspaceId TEXT,createdAt TEXT)"
                    )
                    connection.execute(
                        "INSERT INTO executions VALUES(?,?,?,CURRENT_TIMESTAMP)",
                        (execution_id, "active", workspace_id),
                    )
                control.write_text(
                    json.dumps(
                        {
                            "schema": "aar.autodata.lifecycle-control/v1",
                            "subjects": [
                                {
                                    "kind": "workspace",
                                    "subject_id": workspace_id,
                                    "status": "completed",
                                    "canonical_execution_id": execution_id,
                                },
                                {
                                    "kind": "execution",
                                    "subject_id": execution_id,
                                    "status": "registered",
                                },
                            ],
                        }
                    )
                )
                self.assertEqual(
                    agent._autodata_status_subject(workspace_id), execution_id
                )

                with patch.dict(
                    os.environ, {"AAR_RESUME_APPROVED_PROPOSAL": "1"}, clear=False
                ):
                    resumed = agent._with_resumable_approved_run("original task")
                    self.assertIn("AUTOMATIC RESUME CONTEXT", resumed)
                    self.assertIn(run_id, resumed)

    def test_autodata_status_subject_uses_durable_control_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state.db"
            control = root / "control.json"
            workspace_id = "ws_" + "1" * 32
            meta_id = "exe_" + "2" * 32
            production_id = "exe_" + "3" * 32
            # This is the native schema shape from Trial 7: workspaceId exists,
            # but standalone canonical creation legitimately leaves it NULL.
            with sqlite3.connect(state) as connection:
                connection.execute(
                    "CREATE TABLE executions("
                    "id TEXT,status TEXT,workspaceId TEXT,createdAt TEXT)"
                )
                connection.execute(
                    "INSERT INTO executions VALUES(?,?,NULL,CURRENT_TIMESTAMP)",
                    (meta_id, "active"),
                )
                connection.execute(
                    "CREATE TABLE actions("
                    "id TEXT,kind TEXT,status TEXT,specJson TEXT,createdAt TEXT)"
                )
                connection.execute(
                    "INSERT INTO actions VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
                    (
                        "act_" + "4" * 24,
                        "analyze_results",
                        "pending",
                        json.dumps(
                            {"scope": {"kind": "execution", "id": meta_id}}
                        ),
                    ),
                )
            environment = {
                "AAR_AUTODATA_STATE": str(state),
                "AAR_AUTODATA_SUPERVISOR_CONTROL": str(control),
            }
            control.write_text(
                json.dumps(
                    {
                        "schema": "aar.autodata.lifecycle-control/v1",
                        "subjects": [
                            {
                                "kind": "workspace",
                                "subject_id": workspace_id,
                                "status": "completed",
                                "canonical_execution_id": meta_id,
                            },
                            {
                                "kind": "execution",
                                "subject_id": meta_id,
                                "status": "registered",
                            },
                        ]
                    }
                )
            )
            with patch.dict(os.environ, environment, clear=False):
                resolved = KimiAgent._autodata_status_subject(workspace_id)
                self.assertEqual(resolved, meta_id)
                action = KimiAgent._autodata_pending_action_record(
                    workspace_id, resolved
                )
                self.assertIsNotNone(action)
                self.assertEqual(action["kind"], "analyze_results")

            control.write_text(
                json.dumps(
                    {
                        "schema": "aar.autodata.lifecycle-control/v1",
                        "subjects": [
                            {
                                "kind": "workspace",
                                "subject_id": workspace_id,
                                "status": "completed",
                                "canonical_execution_id": meta_id,
                            },
                            {
                                "kind": "execution",
                                "subject_id": meta_id,
                                "status": "completed",
                                "production_execution_id": production_id,
                            },
                            {
                                "kind": "execution",
                                "subject_id": production_id,
                                "status": "registered",
                                "parent_meta_execution_id": meta_id,
                            },
                        ]
                    }
                )
            )
            with patch.dict(os.environ, environment, clear=False):
                self.assertEqual(
                    KimiAgent._autodata_status_subject(workspace_id), production_id
                )

    def test_autodata_status_subject_fails_closed_on_broken_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            control = Path(temporary) / "control.json"
            workspace_id = "ws_" + "1" * 32
            control.write_text(
                json.dumps(
                    {
                        "schema": "aar.autodata.lifecycle-control/v1",
                        "subjects": [
                            {
                                "kind": "workspace",
                                "subject_id": workspace_id,
                                "status": "completed",
                            }
                        ]
                    }
                )
            )
            with (
                patch.dict(
                    os.environ,
                    {"AAR_AUTODATA_SUPERVISOR_CONTROL": str(control)},
                    clear=False,
                ),
                self.assertRaises(FailureFeedbackError) as failure,
            ):
                KimiAgent._autodata_status_subject(workspace_id)
            self.assertEqual(
                failure.exception.feedback["error_code"],
                "autodata_lineage_invalid",
            )

    def test_autodata_status_subject_keeps_registered_prefreeze_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            control = Path(temporary) / "control.json"
            workspace_id = "ws_" + "1" * 32
            control.write_text(
                json.dumps(
                    {
                        "schema": "aar.autodata.lifecycle-control/v1",
                        "subjects": [
                            {
                                "kind": "workspace",
                                "subject_id": workspace_id,
                                "status": "registered",
                            }
                        ]
                    }
                )
            )
            with patch.dict(
                os.environ,
                {"AAR_AUTODATA_SUPERVISOR_CONTROL": str(control)},
                clear=False,
            ):
                self.assertEqual(
                    KimiAgent._autodata_status_subject(workspace_id), workspace_id
                )

    def test_autodata_subject_status_normalizes_native_shapes(self) -> None:
        workspace_id = "ws_" + "1" * 32
        execution_id = "exe_" + "2" * 32
        self.assertEqual(
            KimiAgent._autodata_subject_status(
                workspace_id,
                {"workspace": {"id": workspace_id, "status": "frozen"}},
            ),
            "frozen",
        )
        self.assertEqual(
            KimiAgent._autodata_subject_status(
                execution_id,
                {"execution_id": execution_id, "status": "active"},
            ),
            "active",
        )
        with self.assertRaises(FailureFeedbackError) as failure:
            KimiAgent._autodata_subject_status(workspace_id, {"status": "active"})
        self.assertEqual(
            failure.exception.feedback["error_code"], "autodata_status_invalid"
        )

    def test_autodata_status_subject_rejects_malformed_control_lineage(self) -> None:
        workspace_id = "ws_" + "1" * 32
        meta_id = "exe_" + "2" * 32
        production_id = "exe_" + "3" * 32
        cases = [
            {
                "schema": "wrong",
                "subjects": [],
            },
            {
                "schema": "aar.autodata.lifecycle-control/v1",
                "subjects": [
                    {
                        "kind": "workspace",
                        "subject_id": workspace_id,
                        "status": "completed",
                        "canonical_execution_id": meta_id,
                    },
                    {
                        "kind": "workspace",
                        "subject_id": workspace_id,
                        "status": "completed",
                        "canonical_execution_id": meta_id,
                    },
                ],
            },
            {
                "schema": "aar.autodata.lifecycle-control/v1",
                "subjects": [
                    {
                        "kind": "workspace",
                        "subject_id": workspace_id,
                        "status": "completed",
                        "canonical_execution_id": meta_id,
                    },
                    {
                        "kind": "execution",
                        "subject_id": meta_id,
                        "status": "completed",
                        "production_execution_id": production_id,
                    },
                    {
                        "kind": "execution",
                        "subject_id": production_id,
                        "status": "registered",
                        "parent_meta_execution_id": "exe_wrong",
                    },
                ],
            },
            {
                "schema": "aar.autodata.lifecycle-control/v1",
                "subjects": [
                    {
                        "kind": "workspace",
                        "subject_id": workspace_id,
                        "status": "completed",
                        "canonical_execution_id": meta_id,
                    },
                    {
                        "kind": "execution",
                        "subject_id": meta_id,
                        "status": "completed",
                        "production_execution_id": production_id,
                    },
                    {
                        "kind": "execution",
                        "subject_id": production_id,
                        "status": "completed",
                        "parent_meta_execution_id": meta_id,
                        "production_execution_id": meta_id,
                    },
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            control = Path(temporary) / "control.json"
            for value in cases:
                with self.subTest(value=value):
                    control.write_text(json.dumps(value))
                    with (
                        patch.dict(
                            os.environ,
                            {"AAR_AUTODATA_SUPERVISOR_CONTROL": str(control)},
                            clear=False,
                        ),
                        self.assertRaises(FailureFeedbackError),
                    ):
                        KimiAgent._autodata_status_subject(workspace_id)

    def test_pipeline_revision_requires_a_real_mutable_strategy_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "draft"
            recipe = root / "reviewed"
            for parent in (draft / "recipe", recipe / "recipe"):
                parent.mkdir(parents=True)
            baseline = json.dumps(
                {
                    "schema": "aar.autodata.generation-strategy/v1",
                    "name": "baseline",
                    "system_prompt": "baseline prompt",
                    "scenario_prompt_prefix": "baseline prefix",
                    "temperature": 0.2,
                }
            )
            current = draft / "recipe" / "generation_strategy.json"
            reviewed = recipe / "recipe" / "generation_strategy.json"
            current.write_text(baseline)
            reviewed.write_text(baseline)
            (draft / "autodata.pipeline.json").write_text("{}")
            action = {
                "id": "act_pipeline_revision",
                "kind": "author_pipeline",
                "spec": {
                    "editable_root": str(draft),
                    "allowed_paths": ["**"],
                    "instructions": "Build the pipeline. Latest feedback: revise it.",
                    "scope": {"kind": "workspace", "revision": 6},
                },
            }
            with patch.dict(
                os.environ,
                {
                    "AAR_AUTODATA_RECIPE_ROOT": str(recipe),
                    "TEAM_DIR": str(root / "team"),
                },
                clear=False,
            ):
                KimiAgent._autodata_capture_pipeline_revision_baseline(action)
                self.assertTrue(
                    KimiAgent._autodata_pipeline_feedback_requires_edit(action)
                )
                context = json.loads(KimiAgent._autodata_editable_context(action))
                self.assertIn("recipe/generation_strategy.json", context)
                current.write_text(baseline.replace("baseline prompt", "hard prompt"))
                self.assertFalse(
                    KimiAgent._autodata_pipeline_feedback_requires_edit(action)
                )
                action["spec"]["scope"]["revision"] = 3
                current.write_text(baseline)
                self.assertFalse(
                    KimiAgent._autodata_pipeline_feedback_requires_edit(action)
                )
                current.write_text(baseline.replace("baseline prefix", "hard prefix"))
                self.assertFalse(
                    KimiAgent._autodata_pipeline_feedback_requires_edit(action)
                )

    def test_action_begin_snapshots_full_record_when_api_response_is_compact(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            strategy = root / "draft" / "recipe" / "generation_strategy.json"
            strategy.parent.mkdir(parents=True)
            strategy.write_text('{"temperature":0.2}')
            action = {
                "id": "act_compact_response",
                "kind": "author_pipeline",
                "status": "pending",
                "spec": {
                    "editable_root": str(root / "draft"),
                    "instructions": "Build it. Latest feedback: revise it.",
                    "scope": {"kind": "workspace", "revision": 6},
                },
            }
            with (
                patch.dict(os.environ, {"TEAM_DIR": str(root / "team")}),
                patch.object(
                    KimiAgent,
                    "_autodata_cli",
                    return_value={
                        "lease_token": "x" * 32,
                        "action": {"id": action["id"], "status": "in_progress"},
                    },
                ),
            ):
                KimiAgent._autodata_begin_action(action)
                snapshot = KimiAgent._autodata_action_snapshot_path(action["id"])
                self.assertEqual(
                    snapshot.read_text().strip(),
                    hashlib.sha256(strategy.read_bytes()).hexdigest(),
                )
                self.assertTrue(
                    KimiAgent._autodata_pipeline_feedback_requires_edit(action)
                )
                strategy.write_text('{"temperature":0.3}')
                self.assertFalse(
                    KimiAgent._autodata_pipeline_feedback_requires_edit(action)
                )

    def test_action_lease_survives_slurm_restart_and_missing_token_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            team = Path(temporary) / "team"
            action_id = "act_" + "4" * 24
            with patch.dict(
                os.environ,
                {"TEAM_DIR": str(team), "SLURM_JOB_ID": "100"},
                clear=False,
            ):
                path = KimiAgent._autodata_action_lease_path(action_id)
                KimiAgent._write_private_text(path, "x" * 32)
            with patch.dict(
                os.environ,
                {"TEAM_DIR": str(team), "SLURM_JOB_ID": "200"},
                clear=False,
            ):
                self.assertEqual(
                    KimiAgent._autodata_require_action_lease(action_id), "x" * 32
                )
                path.unlink()
                with self.assertRaisesRegex(RuntimeError, "durable lease token"):
                    KimiAgent._autodata_require_action_lease(action_id)

    def test_pending_action_lookup_is_scoped_and_rejects_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state.db"
            workspace = "ws_" + "1" * 32
            stale = "ws_" + "2" * 32
            with sqlite3.connect(state) as connection:
                connection.execute(
                    "CREATE TABLE actions("
                    "id TEXT,kind TEXT,status TEXT,specJson TEXT,createdAt TEXT)"
                )
                for suffix, scope in (("1", stale), ("2", workspace)):
                    connection.execute(
                        "INSERT INTO actions VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
                        (
                            "act_" + suffix * 24,
                            "clarify_design",
                            "pending",
                            json.dumps(
                                {
                                    "scope": {
                                        "kind": "workspace",
                                        "id": scope,
                                    }
                                }
                            ),
                        ),
                    )
            with patch.dict(
                os.environ, {"AAR_AUTODATA_STATE": str(state)}, clear=False
            ):
                selected = KimiAgent._autodata_pending_action_record(workspace)
                self.assertEqual(selected["id"], "act_" + "2" * 24)
                with sqlite3.connect(state) as connection:
                    connection.execute(
                        "INSERT INTO actions VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
                        (
                            "act_" + "3" * 24,
                            "author_pipeline",
                            "pending",
                            json.dumps(
                                {
                                    "scope": {
                                        "kind": "workspace",
                                        "id": workspace,
                                    }
                                }
                            ),
                        ),
                    )
                with self.assertRaisesRegex(RuntimeError, "ambiguous"):
                    KimiAgent._autodata_pending_action_record(workspace)

    def test_action_state_query_error_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state.db"
            with sqlite3.connect(state):
                pass
            with patch.dict(
                os.environ, {"AAR_AUTODATA_STATE": str(state)}, clear=False
            ):
                with self.assertRaises(FailureFeedbackError) as failure:
                    KimiAgent._autodata_pending_action_record("ws_" + "1" * 32)
            self.assertEqual(
                failure.exception.feedback["error_code"],
                "autodata_action_state_query_failed",
            )

    def test_stale_supervisor_heartbeat_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status = Path(temporary) / "status.json"
            status.write_text(
                json.dumps(
                    {
                        "schema": "aar.autodata.lifecycle-supervisor/v1",
                        "updated_at": "2020-01-01T00:00:00Z",
                        "state": "idle",
                    }
                )
            )
            environment = {
                "AAR_AUTODATA_LIFECYCLE_SUPERVISED": "1",
                "AAR_AUTODATA_SUPERVISOR_STATUS": str(status),
                "AAR_AUTODATA_SUPERVISOR_HEARTBEAT_SLA_SECONDS": "180",
            }
            with patch.dict(os.environ, environment, clear=False):
                with self.assertRaises(FailureFeedbackError) as failure:
                    KimiAgent._require_fresh_autodata_supervisor_status()
            self.assertEqual(
                failure.exception.feedback["error_code"],
                "autodata_supervisor_heartbeat_invalid",
            )

    def test_stopped_or_unknown_supervisor_state_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status = Path(temporary) / "status.json"
            environment = {
                "AAR_AUTODATA_LIFECYCLE_SUPERVISED": "1",
                "AAR_AUTODATA_SUPERVISOR_STATUS": str(status),
                "AAR_AUTODATA_SUPERVISOR_HEARTBEAT_SLA_SECONDS": "180",
            }
            for state in ("stopped", "mystery"):
                with self.subTest(state=state):
                    status.write_text(
                        json.dumps(
                            {
                                "schema": "aar.autodata.lifecycle-supervisor/v1",
                                "updated_at": time.strftime(
                                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                                ),
                                "state": state,
                            }
                        )
                    )
                    with (
                        patch.dict(os.environ, environment, clear=False),
                        self.assertRaises(FailureFeedbackError) as failure,
                    ):
                        KimiAgent._require_fresh_autodata_supervisor_status()
                    self.assertEqual(
                        failure.exception.feedback["error_code"],
                        "autodata_supervisor_state_invalid",
                    )

    def test_completed_training_without_smoke_marker_fails_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            agent = KimiAgent(
                "test-agent",
                Path(temporary),
                cli_path="/bin/true",
                completion_tool="share_finding",
            )
            environment = {
                "TEAM_DIR": str(Path(temporary) / "team"),
                "AAR_TRAINING_MARKER_GRACE_SECONDS": "0",
                "AAR_KIMI_SCORE_WAIT_SECONDS": "1",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch.object(agent, "_approved_run_id", return_value="run-one"),
                patch.object(agent, "_current_training_job_id", return_value="12345"),
                patch.object(agent, "_current_training_failure", return_value=None),
                patch.object(
                    agent, "_reconcile_terminal_training_job", return_value=None
                ),
                patch.object(
                    agent, "_slurm_job_result", return_value=("COMPLETED", 0)
                ),
            ):
                with self.assertRaises(FailureFeedbackError) as failure:
                    asyncio.run(agent._wait_for_training_smoke_result())
            self.assertEqual(
                failure.exception.feedback["error_code"],
                "training_completed_without_smoke_marker",
            )

    def test_write_guard_allows_only_ideas_tree_and_chain_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ideas = root / "ideas"
            scripts = root / "scripts"
            ideas.mkdir()
            scripts.mkdir()
            memory = root / "logs" / "AGENT_LOG_seed.md"
            env = {
                "AAR_IDEAS_DIR": str(ideas),
                "AAR_AGENT_LOG_PATH": str(memory),
            }

            for destination in (ideas / "candidate" / "run.py", memory):
                allowed, reason = validate_tool_call(
                    {
                        "tool_name": "Write",
                        "tool_input": {"path": str(destination)},
                        "cwd": str(root),
                    },
                    env,
                )
                self.assertTrue(allowed, reason)

            allowed, reason = validate_tool_call(
                {
                    "tool_name": "Edit",
                    "tool_input": {"path": "scripts/submit_train_job.sh"},
                    "cwd": str(root),
                },
                env,
            )
            self.assertFalse(allowed)
            self.assertIn("outside", reason)

            (ideas / "escape").symlink_to(scripts, target_is_directory=True)
            allowed, _ = validate_tool_call(
                {
                    "tool_name": "Write",
                    "tool_input": {"path": "ideas/escape/submit_train_job.sh"},
                    "cwd": str(root),
                },
                env,
            )
            self.assertFalse(allowed)

    def test_write_guard_allows_only_live_autodata_action_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ideas = root / "ideas"
            ideas.mkdir()
            memory = root / "agent-log.md"
            draft = root / "draft"
            draft.mkdir()
            grounding = draft / "grounding"
            grounding.mkdir()
            state = root / "state.db"
            active_id = "act_" + "a" * 24
            pending_id = "act_" + "b" * 24
            completed_id = "act_" + "c" * 24
            spec = {
                "editable_root": str(draft),
                "allowed_paths": ["autodata.workspace.json", "grounding/**"],
            }
            with sqlite3.connect(state) as connection:
                connection.execute(
                    "CREATE TABLE actions("
                    "id TEXT,kind TEXT,status TEXT,specJson TEXT,createdAt TEXT)"
                )
                for action_id, status in (
                    (active_id, "in_progress"),
                    (pending_id, "pending"),
                    (completed_id, "completed"),
                ):
                    connection.execute(
                        "INSERT INTO actions VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
                        (action_id, "clarify_design", status, json.dumps(spec)),
                    )
            env = {
                "AAR_IDEAS_DIR": str(ideas),
                "AAR_AGENT_LOG_PATH": str(memory),
                "AAR_AUTODATA_STATE": str(state),
                "TEAM_DIR": str(root / "team"),
            }
            result_root = root / "team" / "autodata" / "action-results"

            def decision(path: Path) -> tuple[bool, str]:
                return validate_tool_call(
                    {
                        "tool_name": "Write",
                        "tool_input": {"path": str(path)},
                        "cwd": str(root),
                    },
                    env,
                )

            for destination in (
                result_root / f"{active_id}.json",
                draft / "autodata.workspace.json",
                grounding / "manifest.json",
            ):
                allowed, reason = decision(destination)
                self.assertTrue(allowed, reason)

            for destination in (
                result_root / f"{pending_id}.json",
                result_root / f"{completed_id}.json",
                result_root / f"act_{'d' * 24}.json",
                Path(f"/tmp/aar-autodata-{active_id}-result.json"),
                draft / "recipe" / "generation_strategy.json",
                root / "outside.json",
            ):
                allowed, _ = decision(destination)
                self.assertFalse(allowed)

            escape = grounding / "escape"
            escape.symlink_to(root, target_is_directory=True)
            allowed, _ = decision(escape / "outside.json")
            self.assertFalse(allowed)

            safe_target = grounding / "safe-target.json"
            safe_target.write_text("{}")
            safe_link = grounding / "safe-link.json"
            safe_link.symlink_to(safe_target)
            allowed, _ = decision(safe_link)
            self.assertFalse(allowed)

    def test_autodata_action_completion_quotes_leading_hyphen_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            action_id = "act_" + "d" * 24
            result_path = root / "result.json"
            result_path.write_text('{"summary":"done"}')
            with (
                patch.dict(os.environ, {"TEAM_DIR": str(root)}, clear=False),
                patch.object(
                    KimiAgent,
                    "_autodata_action_record",
                    return_value={
                        "id": action_id,
                        "kind": "mutate_candidate",
                        "status": "in_progress",
                        "spec": {"outputs": ["summary"]},
                    },
                ),
                patch.object(KimiAgent, "_autodata_cli") as cli,
            ):
                lease_path = KimiAgent._autodata_action_lease_path(action_id)
                KimiAgent._write_private_text(lease_path, "-" + "x" * 42)
                KimiAgent._autodata_complete_action(action_id, result_path)

            cli.assert_called_once_with(
                "action",
                "complete",
                action_id,
                "--lease-token=-" + "x" * 42,
                "--result",
                str(result_path),
            )
            self.assertFalse(lease_path.exists())
            self.assertFalse(result_path.exists())

    def test_autodata_action_completion_unwraps_valid_aar_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            action_id = "act_" + "e" * 24
            action = {
                "id": action_id,
                "kind": "analyze_results",
                "status": "in_progress",
                "spec": {"outputs": ["proposal", "dashboard_summary"]},
            }
            result_path = root / "result.json"
            result_path.write_text(
                json.dumps(
                    {
                        "schema": "autodata.action-result/v1",
                        "status": "completed",
                        "action_id": action_id,
                        "outputs": {
                            "proposal": "Change one bounded generation setting.",
                            "dashboard_summary": {
                                "headline": "Bounded change",
                                "summary": "Visible evidence supports one change.",
                                "next_step": "Evaluate the candidate.",
                            },
                        },
                    }
                )
            )
            completed_payloads: list[dict[str, object]] = []

            def complete(*arguments: str) -> dict[str, object]:
                completed_payloads.append(
                    json.loads(Path(arguments[-1]).read_text(encoding="utf-8"))
                )
                return {"status": "completed"}

            with (
                patch.dict(os.environ, {"TEAM_DIR": str(root)}, clear=False),
                patch.object(
                    KimiAgent, "_autodata_action_record", return_value=action
                ),
                patch.object(KimiAgent, "_autodata_cli", side_effect=complete),
            ):
                lease_path = KimiAgent._autodata_action_lease_path(action_id)
                KimiAgent._write_private_text(lease_path, "x" * 32)
                KimiAgent._autodata_complete_action(action_id, result_path)

            self.assertEqual(
                completed_payloads,
                [
                    {
                        "proposal": "Change one bounded generation setting.",
                        "dashboard_summary": {
                            "headline": "Bounded change",
                            "summary": "Visible evidence supports one change.",
                            "next_step": "Evaluate the candidate.",
                        },
                    }
                ],
            )
            self.assertFalse(lease_path.exists())
            self.assertFalse(result_path.exists())

    def test_autodata_action_completion_rejects_missing_native_output_for_retry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            action_id = "act_" + "f" * 24
            action = {
                "id": action_id,
                "kind": "analyze_results",
                "status": "in_progress",
                "spec": {"outputs": ["proposal", "dashboard_summary"]},
            }
            result_path = root / "result.json"
            result_path.write_text(
                json.dumps(
                    {
                        "schema": "autodata.action-result/v1",
                        "status": "completed",
                        "action_id": action_id,
                        "outputs": {"dashboard_summary": {}},
                    }
                )
            )
            with (
                patch.dict(os.environ, {"TEAM_DIR": str(root)}, clear=False),
                patch.object(
                    KimiAgent, "_autodata_action_record", return_value=action
                ),
                patch.object(KimiAgent, "_autodata_cli") as cli,
            ):
                lease_path = KimiAgent._autodata_action_lease_path(action_id)
                KimiAgent._write_private_text(lease_path, "x" * 32)
                with self.assertRaisesRegex(
                    AutoDataActionResultValidationError,
                    "missing declared output.*proposal",
                ):
                    KimiAgent._autodata_complete_action(action_id, result_path)
                feedback_path = KimiAgent._autodata_action_result_feedback_path(
                    action_id
                )

            cli.assert_not_called()
            self.assertTrue(lease_path.exists())
            self.assertFalse(result_path.exists())
            self.assertIn("proposal", feedback_path.read_text(encoding="utf-8"))

    def test_host_fsm_immediately_consumes_corrected_action_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            action_id = "act_" + "1" * 24
            action = {
                "id": action_id,
                "kind": "clarify_design",
                "status": "in_progress",
                "spec": {"outputs": ["summary", "decisions"]},
            }
            with (
                patch.dict(os.environ, {"TEAM_DIR": str(root)}, clear=False),
                patch.object(
                    KimiAgent, "_autodata_action_record", return_value=action
                ),
                patch.object(KimiAgent, "_autodata_cli") as cli,
            ):
                lease_path = KimiAgent._autodata_action_lease_path(action_id)
                result_path = KimiAgent._autodata_action_result_path(action_id)
                KimiAgent._write_private_text(lease_path, "x" * 32)
                KimiAgent._write_private_text(
                    result_path,
                    json.dumps(
                        {
                            "schema": "autodata.action-result/v1",
                            "status": "completed",
                            "action_id": action_id,
                            "outputs": {
                                "summary": "Design clarified.",
                                "decisions": ["Use the reviewed recipe."],
                            },
                        }
                    ),
                )

                state = KimiAgent._autodata_consume_action_result(action)

            self.assertEqual(state, "completed")
            cli.assert_called_once()
            self.assertFalse(result_path.exists())
            self.assertFalse(lease_path.exists())

    def test_distinct_action_result_feedback_defers_generic_stall_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            action_id = "act_" + "2" * 24
            action = {
                "id": action_id,
                "kind": "clarify_design",
                "status": "in_progress",
                "spec": {"outputs": ["summary", "decisions"]},
            }
            invalid = json.dumps(
                {
                    "schema": "autodata.action-result/v1",
                    "status": "completed",
                    "action_id": action_id,
                    "outputs": {
                        "summary": "Design clarified.",
                        "decisions": {"choice": "reviewed recipe"},
                    },
                }
            )
            with (
                patch.dict(os.environ, {"TEAM_DIR": str(root)}, clear=False),
                patch.object(
                    KimiAgent, "_autodata_action_record", return_value=action
                ),
                patch.object(KimiAgent, "_autodata_cli") as cli,
            ):
                lease_path = KimiAgent._autodata_action_lease_path(action_id)
                result_path = KimiAgent._autodata_action_result_path(action_id)
                KimiAgent._write_private_text(lease_path, "x" * 32)
                KimiAgent._write_private_text(result_path, invalid)
                first = KimiAgent._autodata_consume_action_result(action)
                KimiAgent._write_private_text(result_path, invalid)
                repeated = KimiAgent._autodata_consume_action_result(action)
                feedback = KimiAgent._autodata_action_result_feedback_path(
                    action_id
                ).read_text(encoding="utf-8").strip()

            self.assertEqual(first, "rejected")
            self.assertEqual(repeated, "unchanged")
            self.assertEqual(
                feedback, "action result output 'decisions' must be a list"
            )
            cli.assert_not_called()

    def test_autodata_progress_signature_tracks_host_owned_reentry_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            team = root / "team"
            run_id = "approved-run"
            action_id = "act_" + "3" * 24
            strategy = root / "draft" / "recipe" / "generation_strategy.json"
            strategy.parent.mkdir(parents=True)
            strategy.write_text('{"temperature":0.2}\n')
            action = {
                "id": action_id,
                "kind": "author_pipeline",
                "status": "in_progress",
                "spec": {"editable_root": str(root / "draft")},
            }
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")
            with (
                patch.dict(
                    os.environ,
                    {"AAR_AUTODATA": "1", "TEAM_DIR": str(team)},
                    clear=False,
                ),
                patch.object(agent, "_autodata_workspace_id", return_value="ws_1"),
                patch.object(
                    agent, "_autodata_status_subject", return_value="execution_1"
                ),
                patch.object(
                    agent, "_autodata_pending_action_record", return_value=action
                ),
            ):
                initial = agent._autodata_lifecycle_progress_signature(run_id)
                strategy.write_text('{"temperature":0.3}\n')
                edited = agent._autodata_lifecycle_progress_signature(run_id)
                result_root = team / "autodata" / "action-results"
                result_root.mkdir(parents=True)
                (result_root / f"{action_id}.validation.txt").write_text(
                    "precise validation feedback\n"
                )
                rejected = agent._autodata_lifecycle_progress_signature(run_id)
                (result_root / f"{action_id}.json").write_text("{}\n")
                corrected = agent._autodata_lifecycle_progress_signature(run_id)
                run_root = team / "autodata" / run_id
                run_root.mkdir(parents=True)
                (run_root / "training-handoff.json").write_text("{}\n")
                handed_off = agent._autodata_lifecycle_progress_signature(run_id)
                (run_root / "training-handoff.verified.json").write_text("{}\n")
                verified = agent._autodata_lifecycle_progress_signature(run_id)

            self.assertNotEqual(initial, edited)
            self.assertNotEqual(edited, rejected)
            self.assertNotEqual(rejected, corrected)
            self.assertNotEqual(corrected, handed_off)
            self.assertNotEqual(handed_off, verified)

    def test_post_turn_action_result_reentry_precedes_generic_stall_check(self) -> None:
        source = Path(KimiAgent._execute_once.__code__.co_filename).read_text()
        self.assertIn("or self._owns_approved_run(output)", source)
        post_turn = source.index(
            "self._autodata_consume_current_action_result(output)"
        )
        stall_check = source.index(
            "progress_signature = self._lifecycle_progress_signature(output)",
            post_turn,
        )
        self.assertLess(post_turn, stall_check)

    def test_stale_approved_marker_is_excluded_from_progress_signature(self) -> None:
        agent = KimiAgent("test-agent", Path.cwd(), cli_path="/bin/true")
        output = {"tool_uses": [], "text_outputs": [], "raw_messages": []}
        with (
            patch.dict(os.environ, {"AAR_AUTODATA": "1"}, clear=False),
            patch.object(agent, "_approved_run_id", return_value="stale-run"),
            patch.object(agent, "_owns_approved_run", return_value=False),
            patch.object(agent, "_current_training_job_id") as training_job,
            patch.object(agent, "_autodata_workspace_id") as workspace_id,
        ):
            signature = agent._lifecycle_progress_signature(output)

        self.assertIsNone(signature[4])
        self.assertIsNone(signature[-1])
        training_job.assert_not_called()
        workspace_id.assert_not_called()

    def test_protected_submission_hash_mismatch_publishes_team_incident(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative_path in PROTECTED_SUBMISSION_FILES:
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("#!/bin/bash\ntrue\n" if path.suffix == ".sh" else "pass\n")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=AAR Test",
                    "-c",
                    "user.email=aar-test@example.com",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                cwd=root,
                check=True,
            )
            corrupted = root / "scripts" / "submit_train_job.sh"
            corrupted.write_text("SCRIPT\n")
            team_dir = root / "team"
            agent = KimiAgent("test-agent", root, cli_path="/bin/true")

            with patch.dict(
                os.environ,
                {"TEAM_DIR": str(team_dir), "IDEA_UID": "chain-alpha"},
                clear=False,
            ), self.assertRaisesRegex(
                OrchestrationIncident, "protected file hash mismatch"
            ):
                agent._validate_protected_submission_files()

            incident = json.loads(
                (team_dir / ".orchestration_incident.json").read_text()
            )
            self.assertEqual(incident["status"], "paused")
            self.assertEqual(incident["stage"], "training_submission")
            self.assertEqual(incident["chain"], "chain-alpha")
            self.assertIn("submit_train_job.sh", incident["error"])
            with patch.dict(
                os.environ, {"TEAM_DIR": str(team_dir)}, clear=False
            ):
                self.assertEqual(incident, agent.active_orchestration_incident())

    def test_orchestration_incident_escapes_kimi_result_wrapping(self) -> None:
        agent = KimiAgent("test-agent", Path.cwd(), cli_path="/bin/true")
        with patch.object(
            agent,
            "_execute_once",
            side_effect=OrchestrationIncident("shared wrapper failed"),
        ), self.assertRaisesRegex(OrchestrationIncident, "shared wrapper failed"):
            asyncio.run(agent.execute("task"))

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
