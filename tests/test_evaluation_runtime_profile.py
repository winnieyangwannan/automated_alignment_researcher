from __future__ import annotations

import pytest

from aar.eval_pod.runtime_profile import evaluation_runtime_profile


def test_transformers_records_effective_fixed_chunk_size() -> None:
    assert evaluation_runtime_profile(
        {
            "EVAL_INFERENCE_BACKEND": "transformers",
            "EVAL_RUN_BATCH": "2",
        }
    ) == {
        "inference_backend": "transformers",
        "submission_mode": "fixed_chunks",
        "batch_size": 2,
    }


def test_vllm_records_scheduler_controls_not_legacy_batch() -> None:
    profile = evaluation_runtime_profile(
        {
            "EVAL_INFERENCE_BACKEND": "vllm",
            "EVAL_RUN_BATCH": "2",
            "EVAL_VLLM_MAX_NUM_SEQS": "256",
            "EVAL_VLLM_MAX_NUM_BATCHED_TOKENS": "32768",
        }
    )

    assert profile == {
        "inference_backend": "vllm",
        "submission_mode": "whole_benchmark_wave",
        "max_num_seqs": 256,
        "max_num_batched_tokens": 32768,
    }
    assert "batch_size" not in profile


def test_resolved_backend_overrides_auto_for_result_metadata() -> None:
    assert evaluation_runtime_profile(
        {"EVAL_INFERENCE_BACKEND": "auto"}, backend="stub"
    ) == {
        "inference_backend": "stub",
        "submission_mode": "in_process",
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EVAL_VLLM_MAX_NUM_SEQS", "0"),
        ("EVAL_VLLM_MAX_NUM_BATCHED_TOKENS", "not-an-integer"),
    ],
)
def test_vllm_rejects_invalid_scheduler_limits(name: str, value: str) -> None:
    environ = {
        "EVAL_INFERENCE_BACKEND": "vllm",
        "EVAL_VLLM_MAX_NUM_SEQS": "256",
        "EVAL_VLLM_MAX_NUM_BATCHED_TOKENS": "32768",
        name: value,
    }
    with pytest.raises(ValueError, match="positive integer"):
        evaluation_runtime_profile(environ)
