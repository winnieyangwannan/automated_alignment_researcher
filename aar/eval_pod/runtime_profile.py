"""Describe the evaluator's effective request-scheduling controls."""
from __future__ import annotations

from collections.abc import Mapping
import os


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def evaluation_runtime_profile(
    environ: Mapping[str, str] | None = None,
    *,
    backend: str | None = None,
) -> dict[str, object]:
    """Return backend-aware batching metadata without changing runtime behavior."""
    env = os.environ if environ is None else environ
    backend = (
        backend or env.get("EVAL_INFERENCE_BACKEND", "transformers")
    ).strip().lower()
    if backend == "hf":
        backend = "transformers"
    if backend not in {"auto", "stub", "transformers", "vllm"}:
        raise ValueError(
            "EVAL_INFERENCE_BACKEND must be auto, vllm, or transformers"
        )

    if backend == "stub":
        return {
            "inference_backend": "stub",
            "submission_mode": "in_process",
        }

    if backend == "vllm":
        token_budget = env.get("EVAL_VLLM_MAX_NUM_BATCHED_TOKENS", "").strip()
        return {
            "inference_backend": "vllm",
            "submission_mode": "whole_benchmark_wave",
            "max_num_seqs": _positive_int(
                env.get("EVAL_VLLM_MAX_NUM_SEQS", "256"),
                "EVAL_VLLM_MAX_NUM_SEQS",
            ),
            "max_num_batched_tokens": (
                _positive_int(token_budget, "EVAL_VLLM_MAX_NUM_BATCHED_TOKENS")
                if token_budget
                else None
            ),
        }

    if backend == "auto":
        return {
            "inference_backend": "auto",
            "submission_mode": "runtime_selected",
        }

    batch = env.get("EVAL_RUN_BATCH") or env.get("EVAL_BATCH_SIZE", "16")
    return {
        "inference_backend": "transformers",
        "submission_mode": "fixed_chunks",
        "batch_size": _positive_int(batch, "evaluation batch size"),
    }
