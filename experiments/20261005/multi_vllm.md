# vLLM target-evaluation backend

Date: 2026-10-05

Branch: `multi_vllm`

Base commit: `b7e6803`

## Decision

Add an in-process vLLM implementation of the existing target-model protocol while retaining the
Transformers implementation as the baseline-compatible default. `EVAL_INFERENCE_BACKEND=auto`
selects vLLM when installed; `vllm` makes its absence fatal; `transformers` preserves the prior path.

The vLLM engine receives every request in a benchmark in one call, uses continuous batching,
prefix caching, and CUDA graphs, and implements both generation and prompt-log-probability scoring.
Multi-GPU evaluation retains the existing one-replica-per-GPU benchmark parallelism.

PEFT submissions remain unmerged runtime LoRAs. For composite checkpoints, adapters trained against
text-only `model.layers` are copied with `model.language_model.layers` keys before vLLM loading. A
fixed continuation is scored with and without the adapter; evaluation fails if its mean token
log-probability effect is at or below `1e-5`.

## Reproducibility boundary

vLLM and Transformers do not consume identical sampling streams. Existing Transformers baselines
must not be used to compute vLLM closed-gap scores. Before production use, remeasure each affected
baseline and confidence interval with `EVAL_INFERENCE_BACKEND=vllm`, then validate representative
base and LoRA checkpoints on the intended GPU architecture.

Linux ARM64 does not receive vLLM from the repository's PyPI dependency marker. The execution
environment must supply a compatible vLLM build; strict backend selection makes a missing build
fail visibly.
