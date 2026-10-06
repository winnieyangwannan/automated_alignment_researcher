# Run 4: Qwen vLLM control preflight

Date: 2026-10-05 (America/Los_Angeles)

## Purpose

This is a small inference-only control experiment to determine whether the vLLM
preflight failure observed with Gemma 4 is model-specific or a general problem
with the new AAR vLLM backend.

This run is not an AAR iteration, benchmark evaluation, or LoRA test. It uses the
same patched evaluator and runtime that were used for the Gemma preflight while
changing only the target model to Qwen.

Interpretation:

- If Qwen completes generation, prompt-logprob scoring, and no-repeat decoding,
  the general vLLM integration works and the earlier weight-loading failure is
  specific to the Gemma 4 implementation in vLLM 0.20.1.
- If Qwen fails in the same weight-loading path, the problem is broader than the
  Gemma model implementation.
- If Qwen loads but fails during decoding or scoring, the AAR vLLM integration
  still needs additional work.

## Reproducibility

- Development branch: `multi_vllm`
- Tested source commit: `c3e27476b48c0a454673ff4cece0c8890661a9be`
- HPC worktree: `/storage/home/winnieyangwn/aar-worktrees/multi_vllm`
- Cluster: `fair-cw-use2-1`
- Partition/QoS: `g3` / `g3_ram_high`
- Allocation: one NVIDIA GB300, 20-minute hard limit
- Model ID: `Qwen/Qwen3.8-27B`
- Local checkpoint: `/checkpoint/ram/shared/models/Qwen/Qwen3.8-27B`
- Checkpoint size: approximately 52 GiB
- Model configuration: `qwen3_5`, 64 layers,
  `Qwen3_5ForConditionalGeneration`
- Python: 3.12
- PyTorch: 2.11.0+cu130
- Transformers: 5.17.0
- vLLM: 0.20.1
- Runtime environment:
  `/storage/home/winnieyangwn/envs/steerability-client`
- Engine settings: `max_model_len=2048`, `max_num_seqs=8`, eager mode,
  prefix caching enabled, BF16

The shared steerability environment is used read-only for this preflight. It is
not yet the production AAR environment.

## Required checks

The preflight must verify:

1. CUDA execution on the requested GB300.
2. Successful Qwen checkpoint loading.
3. Base-model text generation.
4. Prompt-logprob extraction.
5. The vLLM 0.20.1 engine-level no-repeat-ngram processor.
6. Warm generation timing and observed tokens per second.

No universal performance threshold was chosen in advance. The measured warm
throughput will be reported without treating successful execution alone as a
speed result.

## Jobs and logs

The first submission, job `1735355`, exited before model loading because the
smoke-test logging helper received a duplicate Python argument named `name`.
The environment checks passed, but this attempt produced no model result and is
not evidence about Qwen or vLLM.

The corrected shared-environment submission was job `1735364`. It reached
vLLM model initialization but timed out after 19 minutes 20 seconds because of
remote-filesystem stalls while importing and initializing the shared Python
environment. It never completed model loading and did not encounter the Gemma
weight-shape error. This is an environment-startup failure, not a Qwen model
failure.

The successful submission reproduced the known-working Qwen deployment using
the vLLM 0.20.1 container and a detached source worktree pinned exactly to the
tested commit. It was job `1735495`.

Logs:

`/storage/home/winnieyangwn/aar-worktrees/multi_vllm/_runs/qwen_vllm_preflight/qwen-vllm-1735364.log`

`/storage/home/winnieyangwn/aar-worktrees/qwen_vllm_preflight_c3e2747/_runs/qwen_vllm_preflight/qwen-container-1735495.log`

## Result

Passed. Job `1735495` completed successfully in 6 minutes 33 seconds on
`g3-145-003` using one NVIDIA GB300 and exact source commit `c3e2747`.

The proven runtime was:

- vLLM 0.20.1
- PyTorch 2.11.0+cu130
- Transformers 5.7.0
- CUDA 13.0
- `Qwen3_5ForConditionalGeneration`

Measured results:

- Model construction completed in 166.622 seconds.
- All 18 checkpoint shards loaded successfully; weight loading took 35.44
  seconds and used approximately 51.1 GiB for model weights.
- Warm four-prompt generation produced 117 tokens in 4.431 seconds, or 26.402
  tokens per second in eager mode.
- Prompt-logprob scoring returned finite scores `[-28.0891, -27.3352]` in
  1.514 seconds. This verifies the API/plumbing path only; the toy candidates
  were not designed as a semantic-ranking or Transformers-parity assertion.
- The patched engine-level no-repeat-unigram processor generated 24 tokens in
  1.641 seconds.
- The no-repeat assertion found no repeated generated token and no generated
  token copied from the prompt: `duplicate_generated={}`.
- Final GPU memory usage was 228,895 MiB out of 284,208 MiB.

This result confirms that the AAR vLLM backend and its custom V1 logits
processor work for Qwen. The earlier Gemma `512`-versus-`256` failure was
specific to the Gemma 4 model loader in vLLM 0.20.1, not a general vLLM backend
failure.
