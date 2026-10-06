from __future__ import annotations

import os
import queue
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from aar.eval_pod.run_eval import _gpu_worker


ROOT = Path(__file__).resolve().parents[1]


class EvalConcurrencyTest(unittest.TestCase):
    def test_gpu_worker_reuses_loaded_model_for_fingerprint(self) -> None:
        tasks: queue.Queue = queue.Queue()
        results: queue.Queue = queue.Queue()
        specs = [
            SimpleNamespace(
                id=f"bench_{index}",
                name=f"bench_{index}",
                role="safety",
                category="rule",
                extra={},
            )
            for index in range(2)
        ]
        for spec in specs:
            tasks.put(spec)
        tasks.put(None)
        model = SimpleNamespace(close=mock.Mock())
        score = SimpleNamespace(mean=1.0, ci_low=1.0, ci_high=1.0, n=1)
        benchmark = SimpleNamespace(score=mock.Mock(return_value=score))

        with (
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch("aar.benchmarks.registry.discover"),
            mock.patch("aar.eval_pod.run_eval._resolve_judge_fn", return_value=None),
            mock.patch("aar.eval_pod.run_eval.load_model", return_value=model) as load,
            mock.patch("aar.eval_pod.run_eval._apply_golden"),
            mock.patch("aar.eval_pod.run_eval.build_benchmark", return_value=benchmark),
            mock.patch(
                "aar.eval_pod.run_eval._fingerprint_loaded_model",
                return_value="v1:abc",
            ) as fingerprint,
        ):
            _gpu_worker("0", tasks, "model", "secret", results, fingerprint=True)

        messages = [results.get_nowait() for _ in range(4)]
        self.assertEqual(
            [message[0] for message in messages],
            ["score", "score", "fingerprint", "done"],
        )
        load.assert_called_once_with("model")
        fingerprint.assert_called_once_with(model)
        model.close.assert_called_once_with()

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
