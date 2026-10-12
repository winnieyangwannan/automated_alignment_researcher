from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import yaml

from replication.preflight_multidimensional import (
    EXPECTED_BENCHMARKS,
    EXPECTED_CEILING_BENCHMARKS,
    require_exact_budget,
    validate_evaluation_runtime,
    validate_launch_artifacts,
)
from replication.record_multidimensional_baseline import (
    _extract,
    _manifest_contract,
    _profile_contract,
)
from replication.verify_two_iteration_multidimensional import verify


ROOT = Path(__file__).resolve().parents[1]
MODEL = "google/gemma-4-31B-it"


class MultiDimensionalLaunchTest(unittest.TestCase):
    def test_vllm_runtime_validation_ignores_legacy_batch(self) -> None:
        env = {
            "EVAL_INFERENCE_BACKEND": "vllm",
            "EVAL_RUN_BATCH": "not-used",
            "EVAL_VLLM_MAX_NUM_SEQS": "256",
            "EVAL_VLLM_MAX_NUM_BATCHED_TOKENS": "32768",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                validate_evaluation_runtime()["submission_mode"],
                "whole_benchmark_wave",
            )

    def test_transformers_runtime_validation_keeps_batch_contract(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"EVAL_INFERENCE_BACKEND": "transformers", "EVAL_RUN_BATCH": "4"},
            clear=True,
        ):
            with self.assertRaisesRegex(SystemExit, "EVAL_RUN_BATCH=2"):
                validate_evaluation_runtime()

    def test_vllm_runtime_validation_requires_explicit_scheduler_limits(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "EVAL_INFERENCE_BACKEND": "vllm",
                "EVAL_VLLM_MAX_NUM_BATCHED_TOKENS": "32768",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(SystemExit, "EVAL_VLLM_MAX_NUM_SEQS"):
                validate_evaluation_runtime()

    def test_source_baseline_publishes_without_nonexistent_override(self) -> None:
        job = (
            ROOT / "replication" / "baseline_concealing_multidimensional.sbatch"
        ).read_text()
        self.assertIn("unset AAR_BASELINE_OVERRIDES", job)
        self.assertIn("#SBATCH --cpus-per-task=32", job)
        self.assertIn("#SBATCH --gpus=4", job)
        self.assertIn("#SBATCH --mem=384G", job)
        self.assertIn("export EVAL_GPUS=auto", job)
        self.assertIn("export JUDGE_CONCURRENCY=16", job)

    def test_source_result_accepts_canonical_checkpoint_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / "result.json"
            result.write_text(json.dumps({
                "model": "/checkpoint/ram/shared/models/google/gemma-4-31B-it",
                "per_benchmark": {
                    "bench": {
                        "mean": 0.5,
                        "ci_low": 0.4,
                        "ci_high": 0.6,
                        "n": 20,
                    },
                },
            }))
            self.assertEqual(_extract(result, {"bench"})["bench"]["n"], 20)

    def test_source_manifest_accepts_v0_top_level_generation_ceiling(self) -> None:
        contract = _manifest_contract({
            "git_commit": "a" * 40,
            "model": MODEL,
            "judge_backend": "model_api",
            "judge_model": "gpt-5-6-luna",
            "thinking_enabled": True,
            "batch_size": 2,
            "freeform_generation_ceiling": 8192,
        })
        self.assertEqual(contract["generation_ceiling"], 8192)

    def test_reusable_source_profile_does_not_require_same_commit(self) -> None:
        base = {
            "model": MODEL,
            "judge_backend": "model_api",
            "judge_model": "gpt-5-6-luna",
            "thinking_enabled": True,
            "batch_size": 2,
            "generation_ceiling": 8192,
        }
        old = {"git_commit": "a" * 40, **base}
        new = {"git_commit": "b" * 40, **base}
        self.assertEqual(_profile_contract(old), _profile_contract(new))

    def test_launch_requires_exact_separate_caps_and_one_two_iteration_chain(self) -> None:
        launcher = (
            ROOT / "replication" / "launch_two_iteration_multidimensional.sh"
        ).read_text()
        self.assertIn("AAR_CLAUDE_SPEND_CAP_USD=500", launcher)
        self.assertIn("AAR_GPT_JUDGE_SPEND_CAP_USD=500", launcher)
        self.assertIn("AAR_MULTIDIM_SCORING_CONFIRMED=1", launcher)
        self.assertIn("preflight_multidimensional.py\" --launch", launcher)
        self.assertIn("submit_preflights_multidimensional.sh\" --include-web", launcher)
        self.assertIn('launch_team.sh" "pilot" 2 72', launcher)
        self.assertIn("AAR_EVAL_TIME=74:00:00", launcher)
        baseline_job = (
            ROOT / "replication" / "baseline_multidimensional.sbatch"
        ).read_text()
        self.assertIn("#SBATCH --time=36:00:00", baseline_job)
        self.assertNotIn('launch_team.sh" "alpha beta', launcher)
        self.assertIn("AAR_CLAUDE_SESSION_BUDGET_USD=250", launcher)
        self.assertIn("OVERLOADED_MAX_RETRIES=0", launcher)
        self.assertIn("AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1", launcher)
        self.assertIn("AAR_VERIFY_TWO_ITERATION_ARTIFACTS=1", launcher)
        self.assertIn("AAR_FUNCTIONAL_SMOKE=1", launcher)
        submitter = (
            ROOT / "replication" / "submit_preflights_multidimensional.sh"
        ).read_text()
        self.assertIn('source "${SCRIPT_DIR}/env_multidimensional.sh"', submitter)
        self.assertNotIn("env_v0.sh", submitter)
        for name in (
            "setup_env_multidimensional.sbatch",
            "gpu_preflight_multidimensional.sbatch",
            "eval_gpu_preflight_multidimensional.sbatch",
            "smoke_aar_internet_multidimensional.sbatch",
        ):
            source = (ROOT / "replication" / name).read_text()
            self.assertIn("env_multidimensional.sh", source)
            self.assertNotIn("env_v0.sh", source)

    def test_exact_budget_rejects_lower_higher_and_nonfinite_values(self) -> None:
        for value in ("499.99", "500.01", "NaN", "Infinity", ""):
            with self.subTest(value=value), mock.patch.dict(
                os.environ, {"CAP": value}, clear=True
            ):
                with self.assertRaisesRegex(SystemExit, "exactly USD 500"):
                    require_exact_budget("CAP")
        with mock.patch.dict(os.environ, {"CAP": "500.00"}, clear=True):
            self.assertEqual(require_exact_budget("CAP"), "500.00")

    def _artifacts(self, root: Path, head: str) -> tuple[Path, Path, Path]:
        scores = {
            name: {"mean": 0.5, "ci_low": 0.4, "ci_high": 0.6, "n": 20}
            for name in EXPECTED_BENCHMARKS
        }
        baseline = root / "baseline.json"
        baseline.write_text(json.dumps({
            "axis": "honesty_sycophancy_concealing_uncertainty",
            "model": MODEL,
            "status": "canonical_final_commit_composed_baseline",
            "git_commit": head,
            "scores": {MODEL: scores},
        }))
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "phase": "baseline",
            "git_branch": "uv",
            "git_commit": head,
            "model_identity": MODEL,
            "suite_benchmarks": EXPECTED_BENCHMARKS,
            "thinking_enabled": True,
            "judge": {"backend": "model_api", "model": "gpt-5-6-luna"},
            "evaluation_health": {
                "batch_size": 2,
                "freeform_generation_ceiling": 8192,
                "generation_ceiling_benchmarks": EXPECTED_CEILING_BENCHMARKS,
                "fail_on_allocator_warning": True,
                "max_truncation_rate": 0.05,
                "truncation_min_completions": 20,
            },
            "agent_model": "claude-opus-4-8",
            "agent_effort": "max",
            "monitor": {"backend": "model_api", "model": "claude-4-8-opus"},
            "librarian_model": "claude-sonnet-4-6",
            "dimensions": ["honesty", "sycophancy", "concealing_uncertainty"],
            "petri": {"mode": "post_hoc_only", "included_in_optimization": False},
        }))
        dimensions = {
            "mask_factual": "honesty",
            "mask_continuation": "honesty",
            "mask_disinformation": "honesty",
            "sycophancy_eval": "sycophancy",
            "deceptionbench_reward": "honesty",
            "sycon_fp": "sycophancy",
            "llm_uncertainty_bench": "concealing_uncertainty",
            "verbalized_ece": "concealing_uncertainty",
            "abstentionbench": "concealing_uncertainty",
            "sciq_uncertainty": "concealing_uncertainty",
        }
        roles = {
            **{name: "safety" for name in EXPECTED_BENCHMARKS[:7]},
            "deceptionbench_reward": "held_out",
            "sycon_fp": "held_out",
            "sciq_uncertainty": "held_out",
            "mmlu": "capability_filter",
            "gsm8k": "capability_filter",
            "ifeval": "capability_filter",
        }
        entries = []
        for name in EXPECTED_BENCHMARKS:
            entry = {
                "name": name,
                "id": name,
                "category": "rule",
                "role": roles[name],
                "baseline": 0.5,
            }
            if name in dimensions:
                entry.update({
                    "dimension": dimensions[name],
                    "baseline_group": dimensions[name],
                    "evaluation_profile": "gpt_5_6_luna",
                    "baseline_ci_low": 0.4,
                    "baseline_ci_high": 0.6,
                })
            entries.append(entry)
        suite = root / "suite.yaml"
        suite.write_text(yaml.safe_dump({
            "suite": "honesty_sycophancy_concealing_uncertainty",
            "target_model": MODEL,
            "aggregation": "coverage_weighted_geometric_mean",
            "safety_regression_gate": True,
            "dimensions": [
                {"name": "honesty", "weight": 1.0},
                {"name": "sycophancy", "weight": 1.0},
                {"name": "concealing_uncertainty", "weight": 1.0},
            ],
            "evaluation_profiles": {
                "gpt_5_6_luna": {
                    "judge_backend": "model_api",
                    "judge_model": "gpt-5-6-luna",
                    "mask_judge_model": "gpt-5-6-luna",
                },
            },
            "benchmarks": entries,
        }, sort_keys=False))
        return baseline, manifest, suite

    def test_canonical_thirteen_entry_artifacts_and_scoring_contract_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            head = "a" * 40
            paths = self._artifacts(Path(tmp), head)
            validate_launch_artifacts(*paths, head)

    def test_artifact_gate_rejects_scoring_or_commit_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = "a" * 40
            baseline, manifest, suite = self._artifacts(root, head)
            payload = yaml.safe_load(suite.read_text())
            payload["safety_regression_gate"] = False
            suite.write_text(yaml.safe_dump(payload, sort_keys=False))
            with self.assertRaisesRegex(SystemExit, "regression gating"):
                validate_launch_artifacts(baseline, manifest, suite, head)
            with self.assertRaisesRegex(SystemExit, "launch commit"):
                validate_launch_artifacts(baseline, manifest, suite, "b" * 40)

    def test_two_iteration_verifier_requires_sessions_scores_and_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            team = Path(tmp)
            for directory in ("logs", "scores", "forum"):
                (team / directory).mkdir()
            (team / "logs" / "run_summary.json").write_text(json.dumps({
                "sessions": 2,
                "successful_sessions": 2,
                "failed_sessions": 0,
                "stop_reason": "max_iterations",
            }))
            for index in range(2):
                run_id = f"run-{index}"
                session_id = f"session_{index:03d}"
                (team / "logs" / f"{session_id}.log").write_text(
                    "# Result: success=True\n# Ended: now\n"
                )
                per_benchmark = {
                    f"bench-{item}": {"role": "safety" if item < 7 else "capability_filter"}
                    for item in range(10)
                }
                (team / "scores" / f"{run_id}.json").write_text(json.dumps({
                    "suite": "honesty_sycophancy_concealing_uncertainty",
                    "headline_pct": 1.0,
                    "per_benchmark": per_benchmark,
                }))
                (team / "forum" / f"finding-{index}.json").write_text(json.dumps({
                    "finding_type": "result",
                    "run_id": run_id,
                    "aar_session_id": session_id,
                }))
            result = verify(team, 2)
            self.assertTrue(result["ok"])
            self.assertEqual(result["score_run_ids"], ["run-0", "run-1"])

            leaked = _json_path = team / "scores" / "run-0.json"
            payload = json.loads(leaked.read_text())
            payload["per_benchmark"]["held"] = {"role": "held_out"}
            leaked.write_text(json.dumps(payload))
            with self.assertRaisesRegex(SystemExit, "10-entry"):
                verify(team, 2)


if __name__ == "__main__":
    unittest.main()
