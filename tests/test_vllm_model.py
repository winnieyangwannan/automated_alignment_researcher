from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from aar.eval_pod.models import load_model
from aar.eval_pod.vllm_model import (
    NoRepeatNGramLogitsProcessor,
    VLLMModel,
    _round_lora_rank,
    vllm_lora_layout,
)


class FakeLogits(list):
    def __setitem__(self, key, value):
        if isinstance(key, list):
            for index in key:
                super().__setitem__(index, value)
            return
        super().__setitem__(key, value)


class VLLMLoRATests(unittest.TestCase):
    def test_composite_adapter_keys_and_targets_are_translated(self) -> None:
        tensors = {
            "base_model.model.model.layers.0.self_attn.q_proj.lora_A.weight": object(),
            "base_model.model.model.layers.0.self_attn.v_proj.lora_B.weight": object(),
        }
        renamed, config = vllm_lora_layout(tensors, {"target_modules": "old-regex"})
        self.assertEqual(
            sorted(renamed),
            [
                "base_model.model.model.language_model.layers.0.self_attn.q_proj.lora_A.weight",
                "base_model.model.model.language_model.layers.0.self_attn.v_proj.lora_B.weight",
            ],
        )
        self.assertEqual(config["target_modules"], ["q_proj", "v_proj"])

    def test_lora_rank_is_rounded_up_for_vllm_capacity(self) -> None:
        self.assertEqual(_round_lora_rank(4), 8)
        self.assertEqual(_round_lora_rank(16), 16)
        self.assertEqual(_round_lora_rank(48), 64)


class VLLMDecodingTests(unittest.TestCase):
    def test_no_repeat_ngram_processor_bans_only_repeated_continuations(self) -> None:
        logits = FakeLogits([0.0] * 10)
        result = NoRepeatNGramLogitsProcessor(3)([1, 2, 3, 1, 2], logits)
        self.assertEqual(result[3], -float("inf"))
        self.assertEqual(result[2], 0.0)

    def test_three_argument_processor_includes_prompt_tokens(self) -> None:
        logits = FakeLogits([0.0] * 10)
        result = NoRepeatNGramLogitsProcessor(2)([4, 5], [4], logits)
        self.assertEqual(result[5], -float("inf"))

    def test_sequence_scoring_reads_each_chosen_prompt_token(self) -> None:
        model = object.__new__(VLLMModel)
        model._lora_request = "adapter"
        model._sampling_params = lambda *args, **kwargs: (args, kwargs)
        requests = [
            SimpleNamespace(
                prompt_logprobs=[
                    None,
                    {11: SimpleNamespace(logprob=-1.0)},
                    {12: SimpleNamespace(logprob=-2.0)},
                ]
            )
        ]
        model._run = mock.Mock(return_value=requests)
        values = model._sequence_logprobs([[10, 11, 12]], [(1, [11, 12])])
        self.assertEqual(values, [[-1.0, -2.0]])
        model._run.assert_called_once()

    def test_generation_submits_the_entire_benchmark_as_one_scheduler_wave(self) -> None:
        model = object.__new__(VLLMModel)
        model._render = lambda prompt, _: prompt
        model.tokenizer = mock.Mock()
        model.tokenizer.side_effect = lambda text: SimpleNamespace(
            input_ids=[ord(char) for char in text]
        )
        model.tokenizer.decode.side_effect = lambda ids, **_: "".join(
            chr(token_id) for token_id in ids
        )
        model._ctx = 100
        model._auto_ceiling = 8
        model.max_new_tokens = None
        model._sampling_params = lambda max_tokens: max_tokens
        model._generation_count = 0
        model._trunc_count = 0
        model._run = mock.Mock(
            return_value=[
                SimpleNamespace(
                    outputs=[SimpleNamespace(token_ids=[65 + index], finish_reason="stop")]
                )
                for index in range(3)
            ]
        )
        self.assertEqual(model.generate_batch(["one", "two", "three"]), ["A", "B", "C"])
        prompt_ids, max_tokens = model._run.call_args.args
        self.assertEqual(len(prompt_ids), 3)
        self.assertEqual(max_tokens, 8)
        self.assertEqual(model._generation_count, 3)


class BackendSelectionTests(unittest.TestCase):
    def test_explicit_vllm_backend_is_lazy_and_strict(self) -> None:
        sentinel = object()
        with (
            mock.patch.dict(os.environ, {"EVAL_INFERENCE_BACKEND": "vllm"}),
            mock.patch("importlib.util.find_spec", return_value=SimpleNamespace()),
            mock.patch(
                "aar.eval_pod.vllm_model.VLLMModel", return_value=sentinel
            ) as constructor,
        ):
            self.assertIs(load_model("org/model"), sentinel)
        constructor.assert_called_once_with("org/model")

    def test_explicit_vllm_backend_fails_clearly_when_not_installed(self) -> None:
        with (
            mock.patch.dict(os.environ, {"EVAL_INFERENCE_BACKEND": "vllm"}),
            mock.patch("importlib.util.find_spec", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "with vLLM installed"):
                load_model("org/model")

    def test_invalid_backend_is_rejected(self) -> None:
        with mock.patch.dict(
            os.environ, {"EVAL_INFERENCE_BACKEND": "fastish"}, clear=False
        ):
            with self.assertRaisesRegex(ValueError, "auto, vllm, or transformers"):
                load_model("org/model")

    def test_transformers_remains_the_baseline_compatible_default(self) -> None:
        sentinel = object()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("aar.eval_pod.models.HFModel", return_value=sentinel) as constructor,
        ):
            self.assertIs(load_model("org/model"), sentinel)
        constructor.assert_called_once_with("org/model")


if __name__ == "__main__":
    unittest.main()
