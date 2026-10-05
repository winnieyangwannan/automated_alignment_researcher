from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import yaml

from aar.eval_pod.run_eval import _evaluation_profile, load_suite_spec
from scripts import publish_suite


EXPECTED = [
    "mask_factual", "mask_continuation", "mask_disinformation",
    "sycophancy_eval", "llm_uncertainty_bench", "verbalized_ece",
    "abstentionbench", "deceptionbench_reward", "sycon_fp",
    "sciq_uncertainty",
    "mmlu", "gsm8k", "ifeval",
]


class MultiDimensionalSuiteTest(unittest.TestCase):
    def _write(self, payload: dict) -> str:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "suite.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False))
        return str(path)

    def test_catalog_has_exact_thirteen_entries(self) -> None:
        suite_name = "honesty_sycophancy_concealing_uncertainty"
        self.assertEqual(publish_suite.SUITES[suite_name], EXPECTED)
        self.assertEqual(
            set(publish_suite._HELD_OUT[suite_name]),
            {"deceptionbench_reward", "sycon_fp", "sciq_uncertainty"},
        )

    def test_composed_schema_parses_and_profiles_are_scoped(self) -> None:
        benches = []
        for name, dimension in (
            ("h", "honesty"),
            ("s", "sycophancy"),
            ("c", "concealing_uncertainty"),
        ):
            benches.append({
                "name": name,
                "category": "judge",
                "role": "safety",
                "dimension": dimension,
                "baseline_group": dimension,
                "evaluation_profile": "luna",
                "baseline": 0.5,
                "baseline_ci_low": 0.45,
                "baseline_ci_high": 0.55,
            })
        path = self._write({
            "suite": "honesty_sycophancy_concealing_uncertainty",
            "target_model": "google/gemma-4-31B-it",
            "aggregation": "coverage_weighted_geometric_mean",
            "safety_regression_gate": True,
            "dimensions": [
                {"name": "honesty"},
                {"name": "sycophancy"},
                {"name": "concealing_uncertainty"},
            ],
            "evaluation_profiles": {
                "luna": {
                    "judge_backend": "model_api",
                    "judge_model": "gpt-5-6-luna",
                    "mask_judge_model": "gpt-5-6-luna",
                },
            },
            "benchmarks": benches,
        })
        suite, specs = load_suite_spec(path)
        self.assertEqual(suite.aggregation, "coverage_weighted_geometric_mean")
        old = os.environ.get("JUDGE_MODEL")
        os.environ["JUDGE_MODEL"] = "outer"
        try:
            with _evaluation_profile(specs[0]):
                self.assertEqual(os.environ["JUDGE_MODEL"], "gpt-5-6-luna")
            self.assertEqual(os.environ["JUDGE_MODEL"], "outer")
        finally:
            if old is None:
                os.environ.pop("JUDGE_MODEL", None)
            else:
                os.environ["JUDGE_MODEL"] = old

    def test_missing_regression_interval_fails_closed(self) -> None:
        path = self._write({
            "suite": "honesty_sycophancy_concealing_uncertainty",
            "target_model": "google/gemma-4-31B-it",
            "aggregation": "coverage_weighted_geometric_mean",
            "safety_regression_gate": True,
            "dimensions": [
                {"name": "honesty"},
                {"name": "sycophancy"},
                {"name": "concealing_uncertainty"},
            ],
            "benchmarks": [
                {"name": "h", "category": "rule", "role": "safety", "dimension": "honesty"},
                {"name": "s", "category": "rule", "role": "safety", "dimension": "sycophancy"},
                {"name": "c", "category": "rule", "role": "safety", "dimension": "concealing_uncertainty"},
            ],
        })
        with self.assertRaisesRegex(ValueError, "confidence intervals"):
            load_suite_spec(path)


if __name__ == "__main__":
    unittest.main()
