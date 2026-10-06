# Run 5: full Gemma AAR with vLLM evaluation

Run 5 is the first full five-iteration Gemma AAR whose baseline and every
candidate evaluation use the in-process vLLM backend. It is intentionally
isolated from the active `uv` runs.

The pipeline first measures a fresh 13-benchmark base-model baseline with
`docker.io/vllm/vllm-openai:v0.25.1`. Only after that succeeds does it publish
the matching suite, start one four-GB300 evaluator, and start one sequential
five-session Claude Opus 4.8 research chain. Candidate adapters are atomically
merged into full Gemma checkpoints before vLLM scoring; runtime LoRA is not used.

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
source files before creating an attempt directory. The same provenance manifest
is embedded in the retained baseline metadata.

The submission record is retained under the newly created attempt's
`metadata/submission.txt`. The pipeline log records the baseline and, after it
passes, the evaluator and research-chain job IDs.
