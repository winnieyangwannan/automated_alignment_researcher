from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest

from aar.benchmarks.abstentionbench.benchmark import AbstentionBench
from aar.benchmarks.base import BenchmarkSpec


class _Model:
    def generate_batch(self, prompts: list[str], **kwargs) -> list[str]:
        return ["answer" for _ in prompts]


class AbstentionBenchTest(unittest.TestCase):
    def test_injected_judge_calls_run_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            items = [
                {
                    "prompt": f"question {index}",
                    "should_abstain": index % 2 == 0,
                    "dataset": "test",
                    "id": str(index),
                }
                for index in range(4)
            ]
            path = Path(tmp) / "abstentionbench.jsonl"
            path.write_text("".join(json.dumps(item) + "\n" for item in items))
            rendezvous = threading.Barrier(2, timeout=1)

            def judge(_prompt: str) -> bool:
                rendezvous.wait()
                return True

            benchmark = AbstentionBench(
                BenchmarkSpec(name="abstentionbench", category="judge"),
                tmp,
                judge_fn=judge,
            )
            self.assertEqual(benchmark.score(_Model()).n, 4)


if __name__ == "__main__":
    unittest.main()
