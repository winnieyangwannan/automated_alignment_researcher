"""Unit tests for architecture-aware Transformers attention selection."""

from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aar.utils.attention import is_qwen35, select_attention_implementation


class AttentionBackendTest(unittest.TestCase):
    def test_qwen35_defaults_to_sdpa(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                select_attention_implementation(
                    "Qwen/Qwen3.5-2B",
                    available_backends=set(),
                    installed_distributions=set(),
                ),
                "sdpa",
            )

    def test_local_qwen35_checkpoint_is_recognized_from_nested_config(self) -> None:
        config = SimpleNamespace(
            model_type="multimodal",
            text_config=SimpleNamespace(model_type="qwen3_5_text"),
        )
        self.assertTrue(is_qwen35("results/iteration-1/model", config))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                select_attention_implementation(
                    "results/iteration-1/model",
                    config=config,
                    available_backends=set(),
                    installed_distributions=set(),
                ),
                "sdpa",
            )

    def test_qwen35_uses_flash_attention_4_only_with_both_halves(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            selected = select_attention_implementation(
                "Qwen/Qwen3.5-2B",
                available_backends={"sdpa", "flash_attention_4"},
                installed_distributions={"flash_attn_4"},
            )
        self.assertEqual(selected, "flash_attention_4")

    def test_other_models_preserve_caller_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(
                select_attention_implementation(
                    "meta-llama/Llama-3.2-3B-Instruct",
                    available_backends=set(),
                    installed_distributions=set(),
                )
            )
            self.assertEqual(
                select_attention_implementation(
                    "microsoft/Phi-4-mini-instruct",
                    default="eager",
                    available_backends=set(),
                    installed_distributions=set(),
                ),
                "eager",
            )

    def test_registered_flash_attention_4_override_is_honored(self) -> None:
        with patch.dict(
            os.environ,
            {"AAR_ATTN_IMPLEMENTATION": "flash_attention_4"},
            clear=True,
        ):
            self.assertEqual(
                select_attention_implementation(
                    "Qwen/Qwen3.5-2B",
                    available_backends={"flash_attention_4"},
                    installed_distributions={"flash-attn-4"},
                ),
                "flash_attention_4",
            )

    def test_unregistered_flash_attention_4_falls_back_to_sdpa(self) -> None:
        with patch.dict(
            os.environ,
            {"AAR_ATTN_IMPLEMENTATION": "flash_attention_4"},
            clear=True,
        ):
            with self.assertWarnsRegex(RuntimeWarning, "requires both"):
                selected = select_attention_implementation(
                    "Qwen/Qwen3.5-2B",
                    available_backends={"sdpa", "flash_attention_2"},
                    installed_distributions={"flash-attn-4"},
                )
        self.assertEqual(selected, "sdpa")

    def test_registered_flash_attention_4_without_distribution_falls_back(self) -> None:
        with patch.dict(os.environ, {"AAR_ATTN_IMPLEMENTATION": "auto"}, clear=True):
            selected = select_attention_implementation(
                "Qwen/Qwen3.5-2B",
                available_backends={"flash_attention_4"},
                installed_distributions=set(),
            )
        self.assertEqual(selected, "sdpa")


if __name__ == "__main__":
    unittest.main()
