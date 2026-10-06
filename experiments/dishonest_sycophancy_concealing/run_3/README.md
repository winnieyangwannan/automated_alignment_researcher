# Run 3: Gemma 4 vLLM preflight

Date: 2026-10-05 (America/Los_Angeles)

## Purpose

This is an inference-only preflight for the AAR vLLM backend with
`google/gemma-4-31B-it`. Its purpose is to make Gemma 4 generation,
prompt-logprob scoring, and no-repeat decoding work before launching an AAR
evaluation or measuring evaluation speed.

This run is not an AAR iteration or full benchmark evaluation.

## Reference implementation

The known-working reference is:

`/home/winnieyangwn/steerability/eval_script`

The reference setup pins the image:

`docker.io/vllm/vllm-openai:v0.25.1`

The earlier AAR smoke tests used a shared Python environment with vLLM 0.20.1.
That is the key environment difference. The reference workflow also merges a
Gemma LoRA into the base model instead of serving it as a runtime vLLM LoRA.
The current preflight tests only the base model; LoRA validation remains a
separate gate.

## Root cause found in vLLM 0.20.1

Gemma 4 uses heterogeneous attention dimensions:

- Local-attention layers use `head_dim=256`.
- Global-attention layers use `global_head_dim=512`.

The installed vLLM 0.20.1 implementation constructed the relevant parameter as
256-dimensional and then attempted to load a valid 512-dimensional
global-attention weight. Loading failed with:

```text
AssertionError: Attempted to load weight torch.Size([512])
into parameter torch.Size([256])
```

The vLLM 0.25.1 Gemma implementation explicitly recognizes both dimensions.
This makes the observed mismatch a model-loader/version issue rather than a
general CUDA failure or a failure of the AAR no-repeat processor.

## AAR compatibility changes

The following focused commits preceded this run:

- `e1b8b663160c069078923554535e1156a11c9fcf`: migrate custom no-repeat-ngram
  decoding to vLLM's engine-level V1 processor API and request `extra_args`.
- `c3e27476b48c0a454673ff4cece0c8890661a9be`: allow vLLM to inspect Gemma 4's
  heterogeneous Transformers configuration.
- `a9d1ba8632cdbc7c9f6f5fe6f384174f7889992b`: add an observable, timestamped
  vLLM preflight script.

Local validation after the compatibility changes passed 166 tests and 32
subtests.

## Reproducibility

- Development branch: `multi_vllm`
- Current preflight commit: `01076a2`
- HPC worktree: `/storage/home/winnieyangwn/aar-worktrees/multi_vllm`
- Cluster: `fair-cw-use2-1`
- Partition/QoS: `g3` / `g3_ram_high`
- Allocation: one NVIDIA GB300
- Model: `/checkpoint/ram/shared/models/google/gemma-4-31B-it`
- Proven container: `docker.io/vllm/vllm-openai:v0.25.1`
- vLLM settings: `max_model_len=2048`, `max_num_seqs=8`,
  `gpu_memory_utilization=0.70`, prefix caching enabled, eager mode, TP1, BF16
- Custom decoding: AAR no-repeat-ngram processor registered at engine creation

The isolated `multi_vllm` HPC worktree is used for this test. The active `uv`
worktree and its AAR jobs are not modified.

## Required checks

The Gemma preflight must verify:

1. Successful container and CUDA startup on GB300.
2. Successful loading of both local- and global-attention Gemma weights.
3. Base-model text generation.
4. Prompt-logprob extraction.
5. Runtime no-repeat-ngram behavior through the custom vLLM processor.
6. Warm generation timing and observed tokens per second.

After the base model passes, a separate production gate must verify the chosen
LoRA strategy. The reference setup uses merged weights, while the AAR backend
also contains runtime-LoRA support that has not yet been proven for this model.

## Attempts and logs

### vLLM 0.20.1

- Job `1734713` exposed the Transformers 5.17 heterogeneous-config access
  requirement before weight loading.
- Job `1734808` accepted the config fix and reached model startup, but was
  manually cancelled before inference.
- Job `1734895` initialized CUDA/NCCL and began checkpoint loading, then failed
  with the 512-versus-256 Gemma weight mismatch.

The final 0.20.1 log is:

`/storage/home/winnieyangwn/aar-preflight/run/vllm_smoke3-1734895.log`

### vLLM 0.25.1 reproduction

- Job `1735375` exited after 17 seconds because Slurm invoked the wrapped script
  with `/bin/sh`, which does not support `set -o pipefail`. The container and
  model did not start.
- Job `1735379` pulled the correct image, then exited before vLLM import because
  this server image provides `python3`, not `python`.

These are launcher errors and provide no negative inference evidence.

Logs:

- `/storage/home/winnieyangwn/aar-preflight/run/gemma_v025-1735375.log`
- `/storage/home/winnieyangwn/aar-preflight/run/gemma_v025-1735379.log`

The next attempt uses Bash explicitly and invokes `python3` from the image.

### Successful vLLM 0.25.1 preflights

Job `1735398` completed successfully in 11 minutes 36 seconds. It loaded all
58.99 GiB of model weights in approximately 392 seconds and passed every
base-model check:

- Generated `2 + 2 is 4.`
- Produced finite candidate prompt logprobs.
- Preferred the correct candidate ` 4` (`-1.139`) over the incorrect candidate
  (`-11.077`).
- Generated 16 tokens with zero repeated bigrams under the request-scoped
  no-repeat processor.

Log:

`/storage/home/winnieyangwn/aar-preflight/run/gemma_v025-1735398.log`

Commit `01076a2` then made the proven environment requirements explicit:

- Heterogeneous Gemma 4 fails early unless vLLM is at least 0.25.1.
- `language_model_only=True` is passed to match the successful steerability
  deployment.

Job `1735482` revalidated that committed implementation and completed
successfully in 4 minutes 53 seconds. With the checkpoint in page cache, engine
construction took approximately 95 seconds. It again generated
`2 + 2 is 4.`, preferred ` 4` (`-1.226`) over the incorrect candidate
(`-11.226`), and produced zero repeated bigrams.

Log:

`/storage/home/winnieyangwn/aar-preflight/run/gemma_v025_fixed-1735482.log`

The tested image configuration digest was:

`sha256:30a38a1d74a17365eca400e83ffd885b250e0c8c0d3c5b508afa8c412d2ddf95`

## Current status

The base Gemma 4 vLLM preflight passes on the exact vLLM 0.25.1 container used
by the known-working steerability setup. Checkpoint loading, generation,
prompt-logprob scoring, and request-scoped no-repeat decoding are all verified.

The remaining run-2 gate is a real fine-tuned Gemma adapter. The source-truth
steerability workflow merges Gemma adapters into the base checkpoint before
serving; runtime vLLM LoRA has not yet been accepted as equivalent for this
model. The adapter strategy and effect check must be validated before launching
the AAR evaluation.
