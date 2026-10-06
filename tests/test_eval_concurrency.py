from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class EvalConcurrencyTest(unittest.TestCase):
    def test_concurrency_suite_is_public_only_and_size_capped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "source.yaml"
            output = tmp_path / "output.yaml"
            source.write_text(yaml.safe_dump({
                "suite": "example",
                "dimensions": ["selected", "empty"],
                "benchmarks": [
                    {
                        "name": "public_a",
                        "id": "a",
                        "role": "safety",
                        "dimension": "selected",
                        "subset_size": 100,
                    },
                    {"name": "public_b", "id": "b", "role": "capability_filter"},
                    {"name": "secret", "id": "heldout", "role": "held_out"},
                ],
            }))

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "select_eval_concurrency_suite.py"),
                    str(source),
                    str(output),
                    "--benchmark", "a",
                    "--benchmark", "public_b",
                    "--subset-size-cap", "32",
                ],
                check=True,
            )

            suite = yaml.safe_load(output.read_text())
            self.assertEqual([item["id"] for item in suite["benchmarks"]], ["a", "b"])
            self.assertEqual([item["subset_size"] for item in suite["benchmarks"]], [32, 32])
            self.assertEqual(suite["dimensions"], ["selected"])

    def test_concurrency_suite_rejects_heldout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "source.yaml"
            output = tmp_path / "output.yaml"
            source.write_text(yaml.safe_dump({
                "suite": "example",
                "benchmarks": [
                    {"name": "public", "id": "public", "role": "safety"},
                    {"name": "secret", "id": "heldout", "role": "held_out"},
                ],
            }))

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "select_eval_concurrency_suite.py"),
                    str(source),
                    str(output),
                    "--benchmark", "public",
                    "--benchmark", "heldout",
                    "--subset-size-cap", "8",
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("benchmarks missing from source suite", completed.stderr)
