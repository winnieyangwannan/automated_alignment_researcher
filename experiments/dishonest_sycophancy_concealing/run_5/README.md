# Run 5: full Gemma AAR with vLLM evaluation

Run 5 is a full five-iteration Gemma AAR whose candidate evaluations use the
in-process vLLM backend. It is intentionally isolated from the active `uv` runs.

## Worktree mapping

The worktree directory name and checked-out Git branch are different on the
devserver:

- Devserver authoring worktree:
  `/home/winnieyangwn/aar-worktrees/multi_dimensional`
- Devserver branch: `multi_vllm`
- Run-5 source on the devserver:
  `/home/winnieyangwn/aar-worktrees/multi_dimensional/experiments/dishonest_sycophancy_concealing/run_5`
- HPC execution worktree:
  `/storage/home/winnieyangwn/aar-worktrees/multi_vllm`
- HPC branch: `multi_vllm`
- Run-5 source on HPC:
  `/storage/home/winnieyangwn/aar-worktrees/multi_vllm/experiments/dishonest_sycophancy_concealing/run_5`

`multi_dimensional` is the legacy devserver directory name; it does not indicate
the current branch. Make and commit source changes in that devserver worktree,
then synchronize the exact commit to the isolated HPC `multi_vllm` worktree.
Do not edit or advance the active HPC `uv` worktree for this run.

Per the user's explicit 2026-10-06 direction, the run does not recompute the
base-model baseline. It validates and reuses the complete retained 13-benchmark
Gemma baseline, then publishes the matching suite, starts one four-GB300
evaluator, and starts one sequential five-session Claude Opus 4.8 research
chain. Candidate adapters are atomically merged into full Gemma checkpoints
before vLLM scoring; runtime LoRA is not used.

The evaluator fails closed unless its logs show `backend=vllm`, vLLM 0.25.1,
`language_model_only=True`, the exact checkpoint path, and
`lora_strategy=merged_checkpoint`. Scoring errors do not publish completion
scores or silently fall back to Transformers.

`MAX_ITERATIONS=5` counts agent sessions that start, including a session that
fails before publishing a score. Monitoring therefore distinguishes session
count from successful iterations: an iteration is complete only when the same
run ID has an atomic score and a result finding. The run is not reported as five
successful evaluated iterations unless five such pairs exist.

Submit from the synchronized HPC `multi_vllm` worktree:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/multi_vllm
./.venv/bin/python scripts/prepare_llm_uncertainty_source.py
AAR_EXPECTED_BRANCH=multi_vllm \
  AAR_RUNTIME_ROOT=/checkpoint/ram/aar/$USER/vllm_preflight/multi_vllm_env \
  sbatch replication/setup_env_multidimensional.sbatch
# Wait for the environment job to complete successfully, then:
bash experiments/dishonest_sycophancy_concealing/run_5/submit_run_5.sh
```

The preparation command downloads the benchmark author's public Hugging Face
mirror at immutable revision `a199e02b65c6696c467501f01beeb8de9c719916`.
Submission verifies the revision, item counts, and pinned SHA-256 digest of both
source files before creating an attempt directory. The launch revalidates the
same provenance manifest before publishing its suite.

The submitter binds the existing mode-600 HPC `.env` by path and checks only
that the required credential names are nonempty. The launch job receives that
path plus non-secret run configuration; it loads the runtime allowlist itself,
so secret values are not copied into the checkout or embedded in `sbatch`.

The exact retained baseline path and SHA-256, its three source-result hashes,
all 13 scores, and the user-authorized cross-backend reuse decision are retained
in `metadata/baseline_reuse_provenance.json`. The submission record is retained
in `metadata/submission.txt`; the launch log records the evaluator and one
sequential research-chain job ID.
