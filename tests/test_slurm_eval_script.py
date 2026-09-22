"""Focused checks for the portable one-GPU Slurm evaluation launcher."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "slurm_eval.sh"


class SlurmEvalScriptTest(unittest.TestCase):
    def test_smoke_job_resources_are_pinned(self) -> None:
        source = SCRIPT.read_text()
        self.assertIn("#SBATCH --account=ram", source)
        self.assertIn("#SBATCH --partition=g3", source)
        self.assertIn("#SBATCH --qos=g3_ram_high", source)
        self.assertIn("#SBATCH --gpus=1", source)
        self.assertIn("#SBATCH --time=00:30:00", source)

    def test_configurable_paths_and_environment_are_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            repo.mkdir()
            (repo / "aar").mkdir()
            (repo / "scripts").mkdir()
            (repo / "scripts" / "aar_runtime_env.sh").write_text(
                (ROOT / "scripts" / "aar_runtime_env.sh").read_text()
            )
            fake_python = tmp_path / "python"
            fake_python.write_text(
                "#!/bin/bash\n"
                "printf 'cwd=%s\\n' \"$PWD\"\n"
                "printf 'args=%s\\n' \"$*\"\n"
                "printf 'hf=%s\\n' \"$HF_HOME\"\n"
                "printf 'transport=%s\\n' \"$HARNESS_TRANSPORT\"\n"
                "printf 'oai=%s\\n' \"$OAI_API\"\n"
            )
            fake_python.chmod(0o755)
            env_file = tmp_path / "judge.env"
            env_file.write_text("OAI_API=from-file\nIGNORED=value with spaces\n")

            env = os.environ.copy()
            env.update(
                {
                    "HARNESS_REPO": str(repo),
                    "HARNESS_PY": str(fake_python),
                    "HARNESS_ENV": str(env_file),
                    "HF_HOME": str(tmp_path / "hf-cache"),
                    "OAI_API": "inherited",
                }
            )
            completed = subprocess.run(
                ["bash", str(SCRIPT), "run-123", "sycophancy"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertIn(f"cwd={repo}", completed.stdout)
            self.assertIn(
                "args=-u -m aar.eval_pod.entrypoint --run-id run-123 --suite sycophancy",
                completed.stdout,
            )
            self.assertIn(f"hf={tmp_path / 'hf-cache'}", completed.stdout)
            self.assertIn("transport=fs", completed.stdout)
            self.assertIn("oai=inherited", completed.stdout)

    def test_judge_key_can_be_read_from_configurable_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            repo.mkdir()
            (repo / "aar").mkdir()
            (repo / "scripts").mkdir()
            (repo / "scripts" / "aar_runtime_env.sh").write_text(
                (ROOT / "scripts" / "aar_runtime_env.sh").read_text()
            )
            fake_python = tmp_path / "python"
            fake_python.write_text("#!/bin/bash\nprintf 'oai=%s\\n' \"$OAI_API\"\n")
            fake_python.chmod(0o755)
            env_file = tmp_path / "judge.env"
            env_file.write_text("OAI_API=from-file=with-equals\n")
            env = os.environ.copy()
            env.pop("OAI_API", None)
            env.update(
                {
                    "HARNESS_REPO": str(repo),
                    "HARNESS_PY": str(fake_python),
                    "HARNESS_ENV": str(env_file),
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT), "run-456", "sycophancy"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertIn("oai=from-file=with-equals", completed.stdout)


if __name__ == "__main__":
    unittest.main()
