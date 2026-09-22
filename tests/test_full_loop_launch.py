"""Focused portability checks for the FAIR full-loop launch path."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aar.research_loop import monitor


ROOT = Path(__file__).resolve().parents[1]


class FullLoopLaunchTest(unittest.TestCase):
    def test_fair_slurm_defaults_and_no_agent_gpu(self) -> None:
        chain = (ROOT / "scripts" / "slurm_aar_chain.sh").read_text()
        train = (ROOT / "scripts" / "slurm_train_submit.sh").read_text()
        worker = (ROOT / "scripts" / "eval_worker.sh").read_text()

        for source in (chain, train, worker):
            self.assertIn("#SBATCH --account=ram", source)
            self.assertIn("#SBATCH --partition=g3", source)
            self.assertIn("#SBATCH --qos=g3_ram_high", source)
            self.assertNotIn("#SBATCH --partition=general,overflow", source)

        self.assertNotIn("#SBATCH --gpus=", chain)
        self.assertNotIn("#SBATCH --gres=", chain)
        self.assertIn("#SBATCH --gpus=1", train)
        self.assertIn("#SBATCH --gpus=2", worker)

    def test_entrypoints_do_not_assign_legacy_opt_paths(self) -> None:
        names = (
            "slurm_aar_chain.sh",
            "slurm_train_submit.sh",
            "launch_eval_worker.sh",
            "eval_worker.sh",
            "publish_holdout.sh",
        )
        forbidden = (
            "REPO=/opt/aar",
            "PY=/opt/aar",
            "ENV=/opt/aar",
            "HF_HOME=/opt/aar",
        )
        for name in names:
            source = (ROOT / "scripts" / name).read_text()
            with self.subTest(script=name):
                for text in forbidden:
                    self.assertNotIn(text, source)

    def test_submit_wrapper_owns_scheduler_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            sbatch = fake_bin / "sbatch"
            sbatch.write_text("#!/bin/bash\nprintf '%s\\n' \"$*\"\n")
            sbatch.chmod(0o755)
            team = tmp / "team"
            (team / "logs").mkdir(parents=True)
            env = os.environ.copy()
            env.update(
                {
                    "AAR_REPO": str(ROOT),
                    "HARNESS_ENV": str(tmp / "missing.env"),
                    "TEAM_DIR": str(team),
                    "AAR_SLURM_ACCOUNT": "ram",
                    "AAR_SLURM_PARTITION": "g3",
                    "AAR_TRAIN_QOS": "g3_ram_high",
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                }
            )

            completed = subprocess.run(
                ["bash", str(ROOT / "scripts" / "submit_train_job.sh"), "idea", "run-1"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertIn("--account=ram", completed.stdout)
            self.assertIn("--partition=g3", completed.stdout)
            self.assertIn("--qos=g3_ram_high", completed.stdout)
            self.assertIn("--gpus=1", completed.stdout)
            self.assertIn(str(team / "logs" / "train-%j.out"), completed.stdout)
            self.assertIn("slurm_train_submit.sh idea run-1", completed.stdout)

    def test_eval_launcher_caps_honesty_worker_to_requested_gpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            sbatch = fake_bin / "sbatch"
            sbatch.write_text("#!/bin/bash\nprintf '%s\\n' \"$*\"\n")
            sbatch.chmod(0o755)
            holdout = tmp / "holdout"
            suite_dir = holdout / "honesty"
            suite_dir.mkdir(parents=True)
            (suite_dir / "honesty.yaml").write_text(
                "".join(f"- name: bench-{index}\n" for index in range(7))
            )
            team = tmp / "team"
            env = os.environ.copy()
            env.update(
                {
                    "AAR_REPO": str(ROOT),
                    "HARNESS_ENV": str(tmp / "missing.env"),
                    "AXIS": "honesty",
                    "MODEL": "gemma",
                    "HOLDOUT_DIR": str(holdout),
                    "TEAM_DIR": str(team),
                    "AAR_EVAL_GPUS": "2",
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                }
            )

            completed = subprocess.run(
                ["bash", str(ROOT / "scripts" / "launch_eval_worker.sh"), "honesty", "30"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertIn("7 benchmarks -> evaluator gpu:2", completed.stdout)
            self.assertIn("--account=ram", completed.stdout)
            self.assertIn("--partition=g3", completed.stdout)
            self.assertIn("--qos=g3_ram_high", completed.stdout)
            self.assertIn("--gpus=2", completed.stdout)
            self.assertIn("eval_worker.sh honesty 30 auto", completed.stdout)

    def test_prompt_uses_submit_wrapper_and_secure_search_branch(self) -> None:
        source = (ROOT / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()
        self.assertIn("scripts/submit_train_job.sh <your_idea_module>", source)
        self.assertIn("{% if meta_secure_web %}", source)
        self.assertIn("{{ paper_search_helper }} search", source)
        self.assertNotIn("--qos=high --gres=gpu:1", source)

    def test_preflight_is_non_mutating_and_accepts_valid_cpu_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            for name, body in {
                "claude": "if [ \"${1:-}\" = --help ]; then echo --secure-internet-mode; fi\n",
                "sbatch": "exit 0\n",
                "sinfo": "exit 0\n",
                "sacctmgr": "echo 'ram|g3_ram_high'\n",
            }.items():
                command = fake_bin / name
                command.write_text(f"#!/bin/bash\n{body}")
                command.chmod(0o755)
            env_file = tmp / "aar.env"
            env_file.write_text(
                "MODEL_API_KEY=placeholder\n"
                "HF_TOKEN=placeholder\n"
            )
            literature = tmp / "literature"
            literature.mkdir()
            for index in range(30):
                (literature / f"{index}.json").write_text("{}\n")
            before = sorted(path.relative_to(tmp) for path in tmp.rglob("*"))
            env = os.environ.copy()
            env.update(
                {
                    "AAR_REPO": str(ROOT),
                    "HARNESS_PY": sys.executable,
                    "HARNESS_ENV": str(env_file),
                    "AXIS": "honesty",
                    "MODEL": "gemma",
                    "LIT_AXIS_DIR": str(literature),
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                }
            )
            env.pop("SLURM_JOB_ID", None)
            env.pop("CUDA_VISIBLE_DEVICES", None)

            completed = subprocess.run(
                ["bash", str(ROOT / "scripts" / "preflight_aar.sh")],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            after = sorted(path.relative_to(tmp) for path in tmp.rglob("*"))

            self.assertEqual(before, after)
            self.assertIn("30 valid honesty literature entries", completed.stdout)
            self.assertIn("GPU checks require a Slurm GPU allocation", completed.stdout)
            self.assertIn("non-mutating checks complete", completed.stdout)

    def test_monitor_specific_key_precedes_general_key(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "AAR_MONITOR_ANTHROPIC_API_KEY": "monitor-only",
                "ANTHROPIC_API_KEY": "general",
            },
            clear=True,
        ):
            self.assertEqual(monitor._monitor_api_key(), "monitor-only")

    def test_monitor_model_api_key_precedes_general_key(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "AAR_MONITOR_MODEL_API_KEY": "monitor-only",
                "MODEL_API_KEY": "general",
            },
            clear=True,
        ):
            self.assertEqual(monitor._monitor_model_api_key(), "monitor-only")

    def test_monitor_uses_model_api_opus_backend(self) -> None:
        response = '{"approved":true,"violations":[],"reasoning":"ok"}'
        env = {
            "AAR_MONITOR_BACKEND": "model_api",
            "AAR_MONITOR_MODEL_API_KEY": "monitor-only",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch(
                "aar.benchmarks._judge_http.model_api_chat", return_value=response
            ) as call,
        ):
            result = monitor._call_monitor("check", max_tokens=80)

        self.assertTrue(result["approved"])
        self.assertEqual(result["monitor_backend"], "model_api")
        call.assert_called_once_with(
            [{"role": "user", "content": "check"}],
            model="claude-4-8-opus",
            max_tokens=80,
            timeout=150,
        )


if __name__ == "__main__":
    unittest.main()
