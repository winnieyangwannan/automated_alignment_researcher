# Run 6: five parallel Gemma research agents and evaluators

Run 6 launches five independent one-iteration research chains (`alpha` through
`epsilon`) and five evaluator jobs. Each evaluator job requests one four-GPU
GB300 node, so up to five candidates can be evaluated concurrently while each
candidate's 13 benchmarks are dynamically distributed over four local vLLM
replicas.

All evaluator workers consume the same per-team submission queue. Candidate
claims use atomic directory creation, so exactly one worker can claim a run ID.
Candidate PEFT adapters are atomically merged into separate full checkpoints
before evaluation; runtime LoRA and Transformers fallback are forbidden.

The launch fails unless it records five distinct evaluator job IDs and five
distinct research-chain job IDs. `AAR_MAX_CONCURRENT_TRAIN_JOBS=5` also allows
the five agents' one-GPU training jobs to progress concurrently.

Run 6 preserves Run 5's model, benchmark protocol, pinned public-source hashes,
exact 8,192-token generation contract, 10% candidate truncation gate, vLLM
0.25.1 image, and validated scheduler settings. It validates and reuses the
complete retained 13-benchmark base-model baseline and records the same
provenance rather than retraining or recomputing it.

Authoring is on branch `multi_vllm` at
`/home/winnieyangwn/aar-worktrees/multi_dimensional`; execution is isolated to
branch `multi_vllm` at
`/storage/home/winnieyangwn/aar-worktrees/multi_vllm`. Submit only after the
exact committed source has been fast-forwarded to HPC:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/multi_vllm
bash experiments/dishonest_sycophancy_concealing/run_6/submit_run_6.sh
```

The attempt retains the parent launch ID in `metadata/submission.txt`, all ten
child IDs in `metadata/children.env`, and the full launcher transcript in
`metadata/launch_run6_vllm_submission.txt`.
