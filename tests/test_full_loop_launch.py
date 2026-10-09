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
            sbatch_args = tmp / "sbatch-args"
            sbatch = fake_bin / "sbatch"
            sbatch.write_text(
                f"#!/bin/bash\nprintf '%s\\n' \"$*\" > {sbatch_args}\n"
                "printf '12345\\n'\n"
            )
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
                    "AAR_TRAIN_MEM": "128G",
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

            submitted = sbatch_args.read_text()
            self.assertEqual(completed.stdout.strip(), "12345")
            self.assertIn("--account=ram", submitted)
            self.assertIn("--partition=g3", submitted)
            self.assertIn("--qos=g3_ram_high", submitted)
            self.assertIn("--gpus=1", submitted)
            self.assertIn("--mem=128G", submitted)
            self.assertIn(str(team / "logs" / "train-%j.out"), submitted)
            self.assertIn("slurm_train_submit.sh idea run-1", submitted)

    def test_opt_in_receipt_makes_training_submission_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            calls = tmp / "sbatch-calls"
            sbatch = fake_bin / "sbatch"
            sbatch.write_text(
                f"#!/bin/bash\nprintf 'call\\n' >> {calls}\nprintf '12345\\n'\n"
            )
            sbatch.chmod(0o755)
            team = tmp / "team"
            env = os.environ.copy()
            env.update(
                {
                    "AAR_REPO": str(ROOT),
                    "HARNESS_ENV": str(tmp / "missing.env"),
                    "TEAM_DIR": str(team),
                    "AAR_SLURM_ACCOUNT": "ram",
                    "AAR_SLURM_PARTITION": "g3",
                    "AAR_TRAIN_QOS": "g3_ram_high",
                    "AAR_REQUIRE_TRAIN_RECEIPT": "1",
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                }
            )
            command = [
                "bash",
                str(ROOT / "scripts" / "submit_train_job.sh"),
                "idea",
                "run-1",
            ]

            first = subprocess.run(
                command, check=True, capture_output=True, text=True, env=env
            )
            second = subprocess.run(
                command, check=True, capture_output=True, text=True, env=env
            )

            self.assertEqual(first.stdout.strip(), "12345")
            self.assertEqual(second.stdout.strip(), "12345")
            self.assertEqual(calls.read_text().splitlines(), ["call"])
            self.assertEqual(
                (team / ".train_submissions" / "run-1.env").read_text(),
                "run_id=run-1\njob_id=12345\n",
            )

    def test_first_concurrency_limited_submission_initializes_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            sbatch = fake_bin / "sbatch"
            sbatch.write_text("#!/bin/bash\nprintf '12345\\n'\n")
            sbatch.chmod(0o755)
            team = tmp / "team"
            (team / "logs").mkdir(parents=True)
            env = os.environ.copy()
            env.update(
                {
                    "AAR_REPO": str(ROOT),
                    "HARNESS_ENV": str(tmp / "missing.env"),
                    "TEAM_DIR": str(team),
                    "TEAM_ID": "test-team",
                    "AAR_SLURM_ACCOUNT": "ram",
                    "AAR_SLURM_PARTITION": "g3",
                    "AAR_TRAIN_QOS": "g3_ram_high",
                    "AAR_MAX_CONCURRENT_TRAIN_JOBS": "5",
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

            self.assertEqual(completed.stdout.strip(), "12345")
            self.assertEqual(
                (team / ".train_dependency_lanes").read_text().splitlines(),
                ["12345", "", "", "", ""],
            )
            self.assertEqual(
                (team / ".train_dependency_lanes.cursor").read_text(), "1\n"
            )

    def test_opt_in_contract_gate_rejects_before_sbatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            called = tmp / "sbatch-called"
            sbatch = fake_bin / "sbatch"
            sbatch.write_text(f"#!/bin/bash\ntouch {called}\nprintf '12345\\n'\n")
            sbatch.chmod(0o755)
            team = tmp / "team"
            method = team / "methods" / "bad" / "run.py"
            method.parent.mkdir(parents=True)
            method.write_text("def run_experiment(config):\n    return {}\n")
            env = os.environ.copy()
            env.update(
                {
                    "AAR_REPO": str(ROOT),
                    "HARNESS_ENV": str(tmp / "missing.env"),
                    "HARNESS_PY": sys.executable,
                    "TEAM_DIR": str(team),
                    "AAR_IDEAS_DIR": str(team / "methods"),
                    "AAR_REQUIRE_METHOD_CONTRACT": "1",
                    "AAR_SLURM_ACCOUNT": "ram",
                    "AAR_SLURM_PARTITION": "g3",
                    "AAR_TRAIN_QOS": "g3_ram_high",
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                }
            )

            completed = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "submit_train_job.sh"),
                    "bad",
                    "run-1",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(called.exists())

    def test_eval_launcher_caps_honesty_worker_to_requested_gpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            sbatch = fake_bin / "sbatch"
            sbatch.write_text(
                "#!/bin/bash\n"
                "printf '%s\\n' \"$*\"\n"
                "printf 'Submitted batch job %s\\n' \"$$\"\n"
            )
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

            self.assertIn("7 benchmarks -> 1 evaluator worker(s), gpu:2 each", completed.stdout)
            self.assertIn("--account=ram", completed.stdout)
            self.assertIn("--partition=g3", completed.stdout)
            self.assertIn("--qos=g3_ram_high", completed.stdout)
            self.assertIn("--gpus=2", completed.stdout)
            self.assertIn("eval_worker.sh honesty 30 2", completed.stdout)

    def test_eval_launcher_starts_requested_number_of_workers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            sbatch = fake_bin / "sbatch"
            sbatch.write_text(
                "#!/bin/bash\n"
                "printf '%s\\n' \"$*\"\n"
                "printf 'Submitted batch job %s\\n' \"$$\"\n"
            )
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
                    "AAR_EVAL_GPUS": "4",
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                }
            )

            completed = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "launch_eval_worker.sh"),
                    "honesty",
                    "30",
                    "5",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertIn("5 evaluator worker(s), gpu:4 each", completed.stdout)
            self.assertEqual(completed.stdout.count("Submitted batch job"), 5)
            self.assertEqual(completed.stdout.count("--gpus=4"), 5)
            self.assertEqual(completed.stdout.count("eval_worker.sh honesty 30 4"), 5)
            self.assertIn("[launch] evaluator 5/5 -> job", completed.stdout)
            self.assertIn("[launch] evaluator_jobs=", completed.stdout)

    def test_eval_launcher_rejects_zero_workers(self) -> None:
        completed = subprocess.run(
            [
                "bash",
                str(ROOT / "scripts" / "launch_eval_worker.sh"),
                "honesty",
                "30",
                "0",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "AAR_REPO": str(ROOT)},
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("worker count must be at least 1", completed.stderr)

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
                    "AAR_EXPECTED_BRANCH": subprocess.check_output(
                        ["git", "-C", str(ROOT), "branch", "--show-current"],
                        text=True,
                    ).strip(),
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

    def test_monitor_allows_declared_stronger_generator_models(self) -> None:
        policy = monitor._desiderata()
        agent_prompt = (ROOT / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()

        self.assertIn("including models stronger than the target", policy)
        self.assertIn("DECLARED, REPRODUCIBLE TRAINING-DATA PROVENANCE", policy)
        self.assertNotIn("NO LARGER-MODEL DISTILLATION", policy)
        self.assertNotIn("D3", policy)
        self.assertIn("including stronger models", agent_prompt)
        self.assertIn("External model generation is allowed when declared", agent_prompt)
        self.assertNotIn("You may NOT use a larger/stronger model", agent_prompt)
        self.assertNotIn("No distillation from a larger model", agent_prompt)

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
