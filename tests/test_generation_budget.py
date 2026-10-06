from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from aar.benchmarks.base import BenchmarkSpec, run_generation_max_new_tokens
from aar.benchmarks.deceptionbench.benchmark import (
    DECEPTIONBENCH_GENERATION_TOKEN_BUDGET,
)
from aar.benchmarks.mask.benchmark import MASK_GENERATION_TOKEN_BUDGET
from aar.benchmarks.verbalized_ece.benchmark import VerbalizedECE
from aar.eval_pod.models import GENERATION_TOKEN_BUDGET, _context_window


class GenerationBudgetTests(unittest.TestCase):
    def test_target_generation_budget_is_8192(self) -> None:
        self.assertEqual(GENERATION_TOKEN_BUDGET, 8192)
        self.assertEqual(MASK_GENERATION_TOKEN_BUDGET, 8192)
        self.assertEqual(DECEPTIONBENCH_GENERATION_TOKEN_BUDGET, 8192)

    def test_multimodal_config_uses_nested_text_context(self) -> None:
        config = SimpleNamespace(
            max_position_embeddings=None,
            text_config=SimpleNamespace(max_position_embeddings=262_144),
        )
        tokenizer = SimpleNamespace(model_max_length=10**30)
        self.assertEqual(_context_window(config, tokenizer), 262_144)

    def test_invalid_context_metadata_uses_legacy_context_fallback(self) -> None:
        config = SimpleNamespace(
            max_position_embeddings=None,
            text_config=SimpleNamespace(max_position_embeddings=None),
        )
        tokenizer = SimpleNamespace(model_max_length=10**30)
        self.assertEqual(_context_window(config, tokenizer), 4096)

    def test_scoped_run_ceiling_supersedes_short_benchmark_default(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "EVAL_RUN_GEN_CEILING": "8192",
                "EVAL_RUN_GEN_CEILING_BENCHMARKS": (
                    "verbalized_ece abstentionbench"
                ),
            },
            clear=True,
        ):
            self.assertEqual(
                run_generation_max_new_tokens("verbalized_ece", 96), 8192
            )
            self.assertEqual(
                run_generation_max_new_tokens("abstentionbench", 256), 8192
            )
            self.assertEqual(run_generation_max_new_tokens("other", 96), 96)

    def test_invalid_scoped_run_ceiling_fails_closed(self) -> None:
        for invalid in ("0", "-1", "not-an-int"):
            with (
                self.subTest(invalid=invalid),
                mock.patch.dict(
                    os.environ,
                    {
                        "EVAL_RUN_GEN_CEILING": invalid,
                        "EVAL_RUN_GEN_CEILING_BENCHMARKS": "verbalized_ece",
                    },
                    clear=True,
                ),
                self.assertRaisesRegex(ValueError, "positive integer"),
            ):
                run_generation_max_new_tokens("verbalized_ece", 96)

    def test_verbalized_ece_passes_exact_run_ceiling_to_model(self) -> None:
        model = mock.Mock()
        model.generate_batch.return_value = [
            "Answer and Confidence (0-100): yes, 90%"
        ]
        spec = BenchmarkSpec(name="verbalized_ece", category="rule")
        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, "verbalized_ece.jsonl").write_text(
                json.dumps(
                    {
                        "prompt": "Question?",
                        "dataset": "strategyqa",
                        "kind": "bool",
                        "gold": "yes",
                        "id": "item-1",
                    }
                )
                + "\n"
            )
            benchmark = VerbalizedECE(spec, temp_dir)
            with mock.patch.dict(
                os.environ,
                {
                    "EVAL_RUN_GEN_CEILING": "8192",
                    "EVAL_RUN_GEN_CEILING_BENCHMARKS": "verbalized_ece",
                },
                clear=True,
            ):
                benchmark.score(model)
        model.generate_batch.assert_called_once_with(
            ["Question?"], max_new_tokens=8192
        )

if __name__ == "__main__":
    unittest.main()
