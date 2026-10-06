"""Custom vLLM V1 logits processors used by the evaluation backend.

This module intentionally imports vLLM directly.  It is loaded only after the
vLLM backend has been selected, including when an engine worker resolves the
fully-qualified processor class name.
"""
from __future__ import annotations

from typing import Any

from vllm import SamplingParams
from vllm.logits_process import LogitsProcessor as RequestLogitsProcessor
from vllm.v1.sample.logits_processor import AdapterLogitsProcessor

from aar.eval_pod.vllm_model import (
    NoRepeatNGramLogitsProcessor,
    _NO_REPEAT_NGRAM_EXTRA_ARG,
)


class NoRepeatNGramAdapterLogitsProcessor(AdapterLogitsProcessor):
    """Adapt no-repeat-ngram decoding to vLLM's engine-level V1 API."""

    @classmethod
    def validate_params(cls, params: SamplingParams) -> None:
        ngram_size = params.extra_args and params.extra_args.get(
            _NO_REPEAT_NGRAM_EXTRA_ARG
        )
        if ngram_size is None:
            return
        if not isinstance(ngram_size, int) or ngram_size <= 0:
            raise ValueError(
                f"{_NO_REPEAT_NGRAM_EXTRA_ARG} must be a positive integer, "
                f"got {ngram_size!r}"
            )

    def is_argmax_invariant(self) -> bool:
        return False

    def new_req_logits_processor(
        self, params: SamplingParams
    ) -> RequestLogitsProcessor | None:
        ngram_size = params.extra_args and params.extra_args.get(
            _NO_REPEAT_NGRAM_EXTRA_ARG
        )
        if ngram_size is None:
            return None

        processor = NoRepeatNGramLogitsProcessor(ngram_size)

        # The explicit three-argument signature tells AdapterLogitsProcessor to
        # retain prompt token IDs as well as generated IDs.  That matches the
        # Transformers no_repeat_ngram_size behavior used by the baseline.
        def apply_no_repeat_ngram(
            prompt_ids: list[int], output_ids: list[int], logits: Any
        ) -> Any:
            return processor(prompt_ids, output_ids, logits)

        return apply_no_repeat_ngram
