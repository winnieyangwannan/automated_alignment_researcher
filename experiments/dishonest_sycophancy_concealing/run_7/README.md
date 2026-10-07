# Run 7: five parallel 50-iteration Gemma research agents

Run 7 launches five independent research chains (`alpha` through `epsilon`),
each capped at 50 iterations, plus five evaluator jobs. This is a maximum of
250 research sessions. Each evaluator requests one four-GPU GB300 node, so up
to five candidates can be evaluated concurrently while each candidate's 13
benchmarks are dynamically distributed over four local vLLM replicas.

The run otherwise preserves Run 6's protocol: one shared per-team submission
queue with atomic claims, atomically merged candidate checkpoints, no runtime
LoRA or Transformers fallback, five-way training concurrency, the retained
13-benchmark baseline, exact 8,192-token generation contract, 10% candidate
truncation gate, vLLM 0.25.1 image, and validated scheduler settings.

The five chains and evaluators receive a seven-day window. The launch fails
unless it records five distinct evaluator job IDs and five distinct research
chain job IDs, with `max_iterations_per_chain=50` retained in attempt metadata.
As in prior runs, 50 is a session-start cap, not a guarantee of 50 successful
evaluations: successful iterations require matching atomic score/result pairs.

Authoring is on branch `multi_vllm` at
`/home/winnieyangwn/aar-worktrees/multi_dimensional`; execution is isolated to
branch `multi_vllm` at
`/storage/home/winnieyangwn/aar-worktrees/multi_vllm`. Submit only after the
exact committed source has been fast-forwarded to HPC:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/multi_vllm
bash experiments/dishonest_sycophancy_concealing/run_7/submit_run_7.sh
```

The attempt retains the parent launch ID in `metadata/submission.txt`, all ten
child IDs in `metadata/children.env`, and the full launcher transcript in
`metadata/launch_run7_vllm_submission.txt`.

## Phase timing contract

Every generated method must record successful `data_generation`,
`tokenization`, `model_loading`, `training`, and `checkpoint_save` phases with
`aar.phase_timing.phase`. Research-side JSONL is retained under
`TEAM_DIR/timings/<run_id>.research.jsonl`; evaluator-side JSONL is retained
privately under `_eval_private/timings/<run_id>.eval.jsonl`.

The harness also records research-session duration, proposal review, inline
evaluation handoff, finding publication, training queue wait, total method
runtime, model submission, evaluator queue wait, adapter merge, evaluator
setup, model loading, every benchmark (held-out names remain hidden in logs),
composite calculation, private-result persistence, score publication, and
total evaluation runtime.
