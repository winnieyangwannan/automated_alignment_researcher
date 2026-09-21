"""Focused tests for the portable librarian launcher and completion contract."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from aar.litreview import run_litreview


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "litreview.sh"
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
        self.assertIn("#SBATCH --partition=g3", source)
        self.assertIn("#SBATCH --qos=g3_ram_high", source)
        self.assertNotIn("#SBATCH --gres=", source)
        self.assertNotIn("#SBATCH --gpus=", source)
        self.assertIn("LITREVIEW_MODEL:-claude-sonnet-4-6", source)

    def test_all_repaired_scripts_parse(self) -> None:
        for script in PARSE_CHECKED_SCRIPTS:
            with self.subTest(script=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True)

    def test_launcher_uses_configurable_repo_python_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            (repo / "aar").mkdir(parents=True)
            fake_python = tmp_path / "python"
            fake_python.write_text(
                "#!/bin/bash\n"
                "printf 'cwd=%s\\n' \"$PWD\"\n"
                "printf 'args=%s\\n' \"$*\"\n"
                "printf 'forum=%s\\n' \"$LIT_FORUM_DIR\"\n"
                "printf 'workspace=%s\\n' \"$LITREVIEW_WORKSPACE\"\n"
                "printf 'model=%s\\n' \"$LITREVIEW_MODEL\"\n"
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
            ):
                env.pop(name, None)
            env.update(
                {
                    "AAR_REPO": str(repo),
                    "AAR_PYTHON": str(fake_python),
                    "AAR_ENV_FILE": str(env_file),
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
            self.assertIn(
                "args=-u -m aar.litreview.run_litreview --suite sycophancy --min-entries 0",
                completed.stdout,
            )
            self.assertIn(f"forum={axis_dir}", completed.stdout)
            self.assertIn(f"workspace={workspace}", completed.stdout)
            self.assertIn("model=claude-sonnet-4-6", completed.stdout)
            self.assertNotIn("test-placeholder", completed.stdout)

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
            env.update(
                {
                    "AAR_REPO": str(repo),
                    "AAR_PYTHON": str(fake_python),
                    "AAR_ENV_FILE": str(tmp_path / "missing.env"),
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT), "sycophancy", "smoke-team", "1"],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("ANTHROPIC_API_KEY is required", completed.stderr)


class LitreviewCompletionTest(unittest.TestCase):
    def test_count_deduplicates_same_axis_and_forum_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lit_dir = Path(directory)
            (lit_dir / "one.json").write_text("{}")
            with patch.dict(
                os.environ,
                {"LIT_AXIS_DIR": str(lit_dir), "LIT_FORUM_DIR": str(lit_dir / ".")},
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
