from __future__ import annotations

import importlib
import inspect
import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest import mock

from aar.eval_pod.models import load_model
from aar.eval_pod.vllm_model import (
    NoRepeatNGramLogitsProcessor,
    VLLMModel,
    _round_lora_rank,
    vllm_hf_overrides,
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


class VLLMConfigTests(unittest.TestCase):
    def test_heterogeneous_text_config_enables_safe_global_inspection(self) -> None:
        config = SimpleNamespace(
            text_config=SimpleNamespace(is_heterogeneous=True)
        )

        self.assertEqual(
            vllm_hf_overrides(config),
            {
                "text_config": {
                    "allow_global_per_layer_attribute_access": True,
                }
            },
        )

    def test_homogeneous_config_needs_no_override(self) -> None:
        config = SimpleNamespace(
            text_config=SimpleNamespace(is_heterogeneous=False)
        )

        self.assertEqual(vllm_hf_overrides(config), {})


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

    def test_vllm_v1_sampling_params_use_request_extra_args(self) -> None:
        model = object.__new__(VLLMModel)
        model._SamplingParams = mock.Mock(side_effect=lambda **kwargs: kwargs)
        model._no_repeat_ngram = 4
        model._temperature = 0.0
        model._top_p = 1.0
        model._seed = 1234
        model._stop_ids = [2]
        model._vllm_v1_logits_processors = True
        model._vllm_legacy_logits_processors = False

        params = model._sampling_params(16)

        self.assertEqual(
            params["extra_args"], {"aar_no_repeat_ngram_size": 4}
        )
        self.assertNotIn("logits_processors", params)

    def test_prompt_logprobs_do_not_enable_no_repeat_processor(self) -> None:
        model = object.__new__(VLLMModel)
        model._SamplingParams = mock.Mock(side_effect=lambda **kwargs: kwargs)
        model._no_repeat_ngram = 4
        model._temperature = 1.0
        model._top_p = 1.0
        model._seed = 1234
        model._stop_ids = [2]
        model._vllm_v1_logits_processors = True
        model._vllm_legacy_logits_processors = False

        params = model._sampling_params(1, prompt_logprobs=0)

        self.assertNotIn("extra_args", params)
        self.assertEqual(params["prompt_logprobs"], 0)

    def test_vllm_v1_adapter_uses_prompt_and_output_tokens(self) -> None:
        fake_vllm = ModuleType("vllm")
        fake_vllm.SamplingParams = object
        fake_request_logits_processors = ModuleType("vllm.logits_process")
        fake_request_logits_processors.LogitsProcessor = object
        fake_logits_processors = ModuleType("vllm.v1.sample.logits_processor")
        fake_logits_processors.AdapterLogitsProcessor = object
        fake_modules = {
            "vllm": fake_vllm,
            "vllm.logits_process": fake_request_logits_processors,
            "vllm.v1": ModuleType("vllm.v1"),
            "vllm.v1.sample": ModuleType("vllm.v1.sample"),
            "vllm.v1.sample.logits_processor": fake_logits_processors,
        }
        module_name = "aar.eval_pod.vllm_logits_processors"
        sys.modules.pop(module_name, None)
        try:
            with mock.patch.dict(sys.modules, fake_modules):
                module = importlib.import_module(module_name)
                adapter = module.NoRepeatNGramAdapterLogitsProcessor()
                processor = adapter.new_req_logits_processor(
                    SimpleNamespace(
                        extra_args={"aar_no_repeat_ngram_size": 2}
                    )
                )
                self.assertEqual(len(inspect.signature(processor).parameters), 3)
                logits = FakeLogits([0.0] * 10)
                result = processor([4, 5], [4], logits)
                self.assertEqual(result[5], -float("inf"))
        finally:
            sys.modules.pop(module_name, None)

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
