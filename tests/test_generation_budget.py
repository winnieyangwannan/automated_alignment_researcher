from __future__ import annotations

from types import SimpleNamespace
import unittest

from aar.benchmarks.deceptionbench.benchmark import (
    DECEPTIONBENCH_GENERATION_TOKEN_BUDGET,
)
from aar.benchmarks.mask.benchmark import MASK_GENERATION_TOKEN_BUDGET
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

if __name__ == "__main__":
    unittest.main()
