"""Focused tests for the portable librarian launcher and completion contract."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from aar.litreview import run_litreview


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "litreview.sh"
TEAM_SCRIPT = ROOT / "scripts" / "launch_team.sh"
PARSE_CHECKED_SCRIPTS = (
    SCRIPT,
    ROOT / "scripts" / "slurm_aar_chain.sh",
    ROOT / "scripts" / "slurm_train_submit.sh",
    ROOT / "scripts" / "eval_worker.sh",
    ROOT / "scripts" / "eval_watcher.sh",
)

_LIT_FORUM_SPEC = importlib.util.spec_from_file_location(
    "lit_forum_under_test", ROOT / "aar" / "research_loop" / "tools" / "lit_forum.py"
)
assert _LIT_FORUM_SPEC is not None and _LIT_FORUM_SPEC.loader is not None
lit_forum = importlib.util.module_from_spec(_LIT_FORUM_SPEC)
_LIT_FORUM_SPEC.loader.exec_module(lit_forum)


class LitreviewLaunchTest(unittest.TestCase):
    def test_hpc_resources_are_cpu_only_on_requested_partition(self) -> None:
        source = SCRIPT.read_text()
        self.assertIn("#SBATCH --account=ram", source)
        self.assertIn("#SBATCH --partition=g3", source)
        self.assertIn("#SBATCH --qos=g3_ram_high", source)
        self.assertNotIn("#SBATCH --gres=", source)
        self.assertNotIn("#SBATCH --gpus=", source)
        self.assertIn("LITREVIEW_MODEL:-claude-sonnet-4-6", source)

    def test_all_repaired_scripts_parse(self) -> None:
        for script in PARSE_CHECKED_SCRIPTS:
            with self.subTest(script=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True)

    def test_sbatch_entrypoints_use_submit_directory_fallback(self) -> None:
        for name in ("litreview.sh", "slurm_aar_chain.sh", "slurm_train_submit.sh"):
            with self.subTest(script=name):
                source = (ROOT / "scripts" / name).read_text()
                self.assertIn('SLURM_SUBMIT_DIR:-}', source)
                self.assertIn('${SLURM_SUBMIT_DIR}/aar', source)

    def test_team_launcher_gates_chains_on_valid_literature(self) -> None:
        source = TEAM_SCRIPT.read_text()
        self.assertIn('--account="${AAR_SLURM_ACCOUNT:-ram}"', source)
        self.assertIn("--partition=g3 --qos=g3_ram_high", source)
        self.assertIn('--output="${TEAM_DIR}/logs/%x_%j.out"', source)
        self.assertIn("literature survey failed; refusing to launch AAR chains", source)
        self.assertIn("literature baseline has ${n_lit} valid unique entries", source)
        self.assertNotIn("litreview job returned non-zero (continuing)", source)
        self.assertIn('RUNTIME_ROOT="${AAR_RUNTIME_ROOT:-${REPO}/_runs}"', source)

    def test_launcher_uses_configurable_repo_python_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            (repo / "aar").mkdir(parents=True)
            fake_python = tmp_path / "python"
            fake_python.write_text(
                "#!/bin/bash\n"
                "if [ \"${1:-}\" = '-c' ]; then printf '0\\n'; exit 0; fi\n"
                "printf 'cwd=%s\\n' \"$PWD\"\n"
                "printf 'args=%s\\n' \"$*\"\n"
                "printf 'pythonpath=%s\\n' \"$PYTHONPATH\"\n"
                "printf 'forum=%s\\n' \"$LIT_FORUM_DIR\"\n"
                "printf 'workspace=%s\\n' \"$LITREVIEW_WORKSPACE\"\n"
                "printf 'model=%s\\n' \"$LITREVIEW_MODEL\"\n"
                "printf 'cli=%s\\n' \"${CLAUDE_CLI_PATH:-}\"\n"
                "printf 'web=%s\\n' \"${LITREVIEW_WEB_MODE:-}\"\n"
                "printf 'secure=%s\\n' \"${META_CLAUDE_SECURE_INTERNET_MODE:-}\"\n"
            )
            fake_python.chmod(0o755)
            env_file = tmp_path / "research.env"
            env_file.write_text("ANTHROPIC_API_KEY='test-placeholder'\n")
            env = os.environ.copy()
            for name in (
                "ANTHROPIC_API_KEY",
                "LIT_AXIS_DIR",
                "LIT_FORUM_DIR",
                "LITREVIEW_OUTPUT_DIR",
                "LITREVIEW_WORKSPACE",
                "LITREVIEW_MODEL",
                "CLAUDE_CLI_PATH",
            ):
                env.pop(name, None)
            env.update(
                {
                    "AAR_REPO": str(repo),
                    "HARNESS_PY": str(fake_python),
                    "HARNESS_ENV": str(env_file),
                    "PYTHONPATH": "inherited-pythonpath",
                    "PATH": "/usr/bin:/bin",
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT), "sycophancy", "smoke-team", "0"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            axis_dir = repo / "_runs" / "litreview" / "sycophancy"
            workspace = repo / "_runs" / "litreview" / "workspaces" / "smoke-team"
            self.assertIn(f"cwd={repo}", completed.stdout)
            self.assertIn(f"pythonpath={repo}:inherited-pythonpath", completed.stdout)
            self.assertIn(
                "args=-u -m aar.litreview.run_litreview --suite sycophancy --min-entries 0",
                completed.stdout,
            )
            self.assertIn(f"forum={axis_dir}", completed.stdout)
            self.assertIn(f"workspace={workspace}", completed.stdout)
            self.assertIn("model=claude-sonnet-4-6", completed.stdout)
            self.assertIn("cli=\n", completed.stdout)
            self.assertIn("web=native_web", completed.stdout)
            self.assertIn("secure=\n", completed.stdout)
            self.assertNotIn("test-placeholder", completed.stdout)

    def test_launcher_accepts_authenticated_cli_without_direct_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            (repo / "aar").mkdir(parents=True)
            fake_python = tmp_path / "python"
            fake_python.write_text(
                "#!/bin/bash\n"
                "if [ \"${1:-}\" = '-c' ]; then printf '0\\n'; exit 0; fi\n"
                "printf 'cli=%s\\n' \"${CLAUDE_CLI_PATH:-}\"\n"
                "printf 'web=%s\\n' \"${LITREVIEW_WEB_MODE:-}\"\n"
                "printf 'secure=%s\\n' \"${META_CLAUDE_SECURE_INTERNET_MODE:-}\"\n"
            )
            fake_python.chmod(0o755)
            fake_cli = tmp_path / "claude"
            fake_cli.write_text("#!/bin/bash\nexit 0\n")
            fake_cli.chmod(0o755)
            env_file = tmp_path / "research.env"
            env_file.write_text("# no direct Anthropic key\n")
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            env.update(
                {
                    "AAR_REPO": str(repo),
                    "HARNESS_PY": str(fake_python),
                    "HARNESS_ENV": str(env_file),
                    "CLAUDE_CLI_PATH": str(fake_cli),
                    "META_CLAUDE_SECURE_INTERNET_MODE": "1",
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT), "sycophancy", "cli-team", "0"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertIn(f"cli={fake_cli}", completed.stdout)
            self.assertIn("web=native_web", completed.stdout)
            self.assertIn("secure=\n", completed.stdout)

    def test_launcher_prefers_cli_and_removes_direct_key_from_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            (repo / "aar").mkdir(parents=True)
            helper = repo / "scripts" / "aar-paper-search"
            helper.parent.mkdir()
            helper.write_text("#!/bin/bash\nexit 0\n")
            helper.chmod(0o755)
            fake_python = tmp_path / "python"
            fake_python.write_text(
                "#!/bin/bash\n"
                "if [ \"${1:-}\" = '-c' ]; then printf '0\\n'; exit 0; fi\n"
                "printf 'cli=%s\\n' \"${CLAUDE_CLI_PATH:-}\"\n"
                "if [ -n \"${ANTHROPIC_API_KEY:-}\" ]; then\n"
                "  printf 'key=set\\n'\n"
                "else\n"
                "  printf 'key=unset\\n'\n"
                "fi\n"
                "printf 'web=%s\\n' \"${LITREVIEW_WEB_MODE:-}\"\n"
                "printf 'secure=%s\\n' \"${META_CLAUDE_SECURE_INTERNET_MODE:-}\"\n"
                "printf 'model_api=%s\\n' \"${MODEL_API_KEY:+set}\"\n"
                "printf 'hf=%s\\n' \"${HF_TOKEN:+set}\"\n"
            )
            fake_python.chmod(0o755)
            fake_cli = tmp_path / "claude"
            fake_cli.write_text("#!/bin/bash\nexit 0\n")
            fake_cli.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "AAR_REPO": str(repo),
                    "HARNESS_PY": str(fake_python),
                    "HARNESS_ENV": str(tmp_path / "missing.env"),
                    "CLAUDE_CLI_PATH": str(fake_cli),
                    "AAR_FAIR_CLAUDE_CLI_PATH": str(fake_cli),
                    "ANTHROPIC_API_KEY": "must-not-reach-child",
                    "MODEL_API_KEY": "must-not-reach-child",
                    "HF_TOKEN": "must-not-reach-child",
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT), "sycophancy", "precedence-team", "0"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertIn(f"cli={fake_cli}", completed.stdout)
            self.assertIn("key=unset", completed.stdout)
            self.assertIn("web=meta_secure", completed.stdout)
            self.assertIn("secure=1", completed.stdout)
            self.assertIn("model_api=", completed.stdout)
            self.assertIn("hf=", completed.stdout)
            self.assertNotIn("must-not-reach-child", completed.stdout)

    def test_launcher_rejects_missing_credential_without_running_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            (repo / "aar").mkdir(parents=True)
            fake_python = tmp_path / "python"
            fake_python.write_text("#!/bin/bash\nexit 99\n")
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            env.pop("CLAUDE_CLI_PATH", None)
            env.update(
                {
                    "AAR_REPO": str(repo),
                    "HARNESS_PY": str(fake_python),
                    "HARNESS_ENV": str(tmp_path / "missing.env"),
                    "PATH": "/usr/bin:/bin",
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT), "sycophancy", "smoke-team", "1"],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn(
                "neither ANTHROPIC_API_KEY nor an executable Claude CLI is available",
                completed.stderr,
            )

    def test_slurm_spool_copy_resolves_submit_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            (repo / "aar").mkdir(parents=True)
            python = repo / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text(
                "#!/bin/bash\n"
                "if [ \"${1:-}\" = '-c' ]; then printf '0\\n'; exit 0; fi\n"
                "printf 'cwd=%s\\n' \"$PWD\"\n"
            )
            python.chmod(0o755)
            (repo / ".env").write_text("ANTHROPIC_API_KEY='test-placeholder'\n")
            spool = tmp_path / "slurm-spool"
            spool.mkdir()
            spooled_script = spool / "slurm_script"
            spooled_script.write_text(SCRIPT.read_text())

            env = os.environ.copy()
            for name in (
                "AAR_REPO",
                "HARNESS_PY",
                "HARNESS_ENV",
                "ANTHROPIC_API_KEY",
                "CLAUDE_CLI_PATH",
                "AAR_FAIR_CLAUDE_CLI_PATH",
            ):
                env.pop(name, None)
            env["SLURM_SUBMIT_DIR"] = str(repo)
            env["PATH"] = "/usr/bin:/bin"

            completed = subprocess.run(
                ["bash", str(spooled_script), "sycophancy", "slurm-team", "0"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertIn(f"cwd={repo}", completed.stdout)
            self.assertNotIn("test-placeholder", completed.stdout)

    def test_survey_forwards_resolved_cli_path_to_base_agent(self) -> None:
        captured: dict[str, object] = {}

        class FakeAgent:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

            async def execute(self, task: str) -> None:
                captured["task"] = task

        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "claude"
            cli.write_text("#!/bin/bash\nexit 0\n")
            cli.chmod(0o755)
            agent_module = types.ModuleType("aar.research_loop.agent")
            agent_module.BaseAgent = FakeAgent
            lit_forum_module = types.ModuleType("aar.research_loop.tools.lit_forum")
            lit_forum_module.count = lambda: 0
            with (
                patch.dict(
                    os.environ,
                    {
                        "CLAUDE_CLI_PATH": str(cli),
                        "LITREVIEW_WEB_MODE": "meta_secure",
                    },
                    clear=False,
                ),
                patch.dict(
                    sys.modules,
                    {
                        "aar.research_loop.agent": agent_module,
                        "aar.research_loop.tools.lit_forum": lit_forum_module,
                    },
                ),
            ):
                asyncio.run(
                    run_litreview._survey(
                        "general", "General {axis}", "sycophancy", 1,
                        "claude-sonnet-4-6", Path(directory), {},
                    )
                )

        self.assertEqual(captured["cli_path"], str(cli))
        helper = run_litreview._paper_search_helper()
        self.assertEqual(
            captured["allowed_tools"],
            [
                f"Bash({helper} *)",
                "mcp__server-api-tools__get_literature",
                "mcp__server-api-tools__share_literature",
            ],
        )
        self.assertEqual(captured["permission_mode"], "dontAsk")
        self.assertIn(f"`{helper} search", captured["task"])
        self.assertNotIn("WebSearch", captured["allowed_tools"])
        self.assertNotIn("Read", captured["allowed_tools"])
        self.assertNotIn("Write", captured["allowed_tools"])

    def test_native_web_mode_preserves_portable_tools(self) -> None:
        with patch.dict(
            os.environ, {"LITREVIEW_WEB_MODE": "native_web"}, clear=False
        ):
            allowed, permission_mode, prompt, _ = run_litreview._web_config()

        self.assertEqual(permission_mode, "bypassPermissions")
        self.assertIn("WebSearch", allowed)
        self.assertIn("WebFetch", allowed)
        self.assertIn("**WebSearch**", prompt)

    def test_unknown_web_mode_fails_closed(self) -> None:
        with (
            patch.dict(os.environ, {"LITREVIEW_WEB_MODE": "unknown"}, clear=False),
            self.assertRaisesRegex(RuntimeError, "unsupported LITREVIEW_WEB_MODE"),
        ):
            run_litreview._web_config()


class LitreviewCompletionTest(unittest.TestCase):
    def test_count_deduplicates_same_axis_and_forum_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lit_dir = Path(directory)
            (lit_dir / "one.json").write_text('{"id": "one"}')
            with patch.dict(
                os.environ,
                {"LIT_AXIS_DIR": str(lit_dir), "LIT_FORUM_DIR": str(lit_dir / ".")},
                clear=False,
            ):
                self.assertEqual(lit_forum.count(), 1)

    def test_count_deduplicates_ids_across_distinct_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            axis_dir = root / "axis"
            forum_dir = root / "forum"
            axis_dir.mkdir()
            forum_dir.mkdir()
            (axis_dir / "axis-copy.json").write_text('{"id": "same", "method": "axis"}')
            (forum_dir / "forum-copy.json").write_text('{"id": "same", "method": "forum"}')
            with patch.dict(
                os.environ,
                {"LIT_AXIS_DIR": str(axis_dir), "LIT_FORUM_DIR": str(forum_dir)},
                clear=False,
            ):
                self.assertEqual(lit_forum.count(), 1)
                self.assertEqual(len(lit_forum.read_lit_entries()), 1)

    def test_count_ignores_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lit_dir = Path(directory)
            (lit_dir / "valid.json").write_text('{"id": "valid"}')
            (lit_dir / "broken.json").write_text("not-json")
            with patch.dict(
                os.environ,
                {"LIT_AXIS_DIR": str(lit_dir), "LIT_FORUM_DIR": ""},
                clear=False,
            ):
                self.assertEqual(lit_forum.count(), 1)

    def test_incomplete_survey_fails_the_job(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "produced 0 entries; target was 1"):
            run_litreview._require_minimum(0, 1)

    def test_complete_survey_passes(self) -> None:
        run_litreview._require_minimum(30, 30)


if __name__ == "__main__":
    unittest.main()
