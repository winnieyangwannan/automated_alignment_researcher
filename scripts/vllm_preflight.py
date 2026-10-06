#!/usr/bin/env python3
"""Run a small, observable target-model preflight through the evaluator backend."""

from __future__ import annotations

import importlib.metadata
import json
import math
import os
import platform
import socket
import time
from datetime import datetime, timezone


def emit(event: str, **values: object) -> None:
    """Print one unbuffered machine-readable progress event."""
    print(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **values,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def main() -> None:
    model_path = os.environ["AAR_PREFLIGHT_MODEL"]
    max_new_tokens = int(os.getenv("AAR_PREFLIGHT_MAX_NEW_TOKENS", "16"))
    emit(
        "script_started",
        hostname=socket.gethostname(),
        architecture=platform.machine(),
        python=platform.python_version(),
        git_sha=os.environ.get("AAR_PREFLIGHT_SHA"),
        model_path=model_path,
        slurm_job_id=os.environ.get("SLURM_JOB_ID"),
    )

    emit("torch_import_started")
    import torch

    emit("torch_import_complete", torch=torch.__version__)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available inside the GPU allocation")
    props = torch.cuda.get_device_properties(0)
    emit(
        "cuda_verified",
        cuda_runtime=torch.version.cuda,
        gpu=props.name,
        gpu_memory_gib=round(props.total_memory / 2**30, 2),
    )

    emit("evaluator_vllm_import_started")
    from aar.eval_pod.vllm_model import VLLMModel

    emit(
        "evaluator_vllm_import_complete",
        transformers=importlib.metadata.version("transformers"),
        vllm=importlib.metadata.version("vllm"),
    )
    load_started = time.perf_counter()
    emit("llm_construction_started")
    model = VLLMModel(model_path, max_new_tokens=max_new_tokens)
    emit(
        "llm_construction_complete",
        seconds=round(time.perf_counter() - load_started, 3),
    )

    try:
        model.apply_decoding(
            no_repeat_ngram=0,
            max_new_tokens=max_new_tokens,
            temperature=0.0,
            top_p=1.0,
            seed=1234,
        )
        emit("generation_started")
        generation_started = time.perf_counter()
        generated_text = model.generate("In one short sentence, what is 2 + 2?")
        emit(
            "generation_complete",
            seconds=round(time.perf_counter() - generation_started, 6),
            text=generated_text,
        )

        emit("prompt_logprobs_started")
        logprob_started = time.perf_counter()
        scores = model.candidate_logits(
            "The result of 2 + 2 is", [" 4", " 5"], use_chat_template=False
        )
        if len(scores) != 2 or not all(math.isfinite(score) for score in scores):
            raise RuntimeError(f"invalid prompt log-probability scores: {scores!r}")
        emit(
            "prompt_logprobs_complete",
            seconds=round(time.perf_counter() - logprob_started, 6),
            scores=scores,
            preferred_candidate=[" 4", " 5"][scores.index(max(scores))],
        )

        model.apply_decoding(
            no_repeat_ngram=2,
            max_new_tokens=max_new_tokens,
            temperature=0.0,
            top_p=1.0,
        )
        raw_prompt = "Continue briefly: red blue red blue"
        prompt_ids = model.tokenizer(raw_prompt).input_ids
        params = model._sampling_params(max_new_tokens)
        emit(
            "no_repeat_ngram_started",
            request_extra_args=getattr(params, "extra_args", None),
        )
        no_repeat_started = time.perf_counter()
        request = model._run([prompt_ids], params)[0]
        output_ids = list(request.outputs[0].token_ids)
        if not output_ids:
            raise RuntimeError("no-repeat request produced no output tokens")

        all_ids = list(prompt_ids)
        seen = {
            tuple(all_ids[index - 1 : index + 1])
            for index in range(1, len(all_ids))
        }
        violations: list[tuple[int, int]] = []
        for token_id in output_ids:
            all_ids.append(token_id)
            ngram = tuple(all_ids[-2:])
            if ngram in seen:
                violations.append(ngram)
            seen.add(ngram)
        if violations:
            raise RuntimeError(
                "no-repeat processor allowed repeated generated bigrams: "
                f"{violations!r}"
            )
        emit(
            "no_repeat_ngram_complete",
            seconds=round(time.perf_counter() - no_repeat_started, 6),
            output_tokens=len(output_ids),
            repeated_generated_bigrams=len(violations),
            text=model.tokenizer.decode(output_ids, skip_special_tokens=True),
        )
        emit("result", passed=True)
    finally:
        emit("llm_shutdown_started")
        model.close()
        emit("llm_shutdown_complete")


if __name__ == "__main__":
    main()
