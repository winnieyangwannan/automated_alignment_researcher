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

## Current durable continuation and result paths

The original Run 7 attempt under `/checkpoint/ram` became inaccessible through
NFS. The active continuation therefore writes to durable `/storage/home`
instead of that old namespace. As of 2026-10-07 20:43 UTC, all five continuation
chains and all five evaluators are running from commit
`a8fdf5b066294089e974e2e979c04bb60b3139d5`.

The canonical continuation attempt is:

```text
/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/full_attempts/20261007T203258Z-a8fdf5b06629
```

The active team directory is:

```text
/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/full_attempts/20261007T203258Z-a8fdf5b06629/aar_teams/honesty-sycophancy-concealing-gemma4_31b-opus48-run7-storage-continuation-1750282
```

Within that team directory:

- `scores/*.json` contains newly completed public score records. A new Run 7
  continuation iteration is counted only when its score has a matching finding.
- `forum/*.json` contains the 14 reconstructed retained findings plus new
  findings as chains complete evaluations.
- `logs/AGENT_LOG_gemma4_31b_explore_<chain>.md` is the durable running memory
  for each of `alpha`, `beta`, `gamma`, `delta`, and `epsilon`.
- `logs/session_*_<chain>_*.log` contains individual research-session logs.
- `logs/aar-*-<chain>_<job-id>.out` contains each chain's Slurm output.
- `_eval_private/eval_worker_<job-id>.out` contains evaluator operational logs,
  including the fail-closed vLLM markers. Evaluator-private material must not be
  copied into research prompts or findings.
- `_eval_private/merge_manifests/*.json` retains merge provenance after each
  node-local merged checkpoint is deleted.

The attempt-level metadata is under `metadata/`. In particular,
`metadata/submission.txt` records launch job `1750282`, and
`metadata/children.env` records evaluator jobs `1750344` through `1750348` and
chain jobs `1750349` through `1750353` in alpha-to-epsilon order.

To inspect new durable results on `fair-cw-use2-1`:

```bash
export RUN7_ATTEMPT=/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/full_attempts/20261007T203258Z-a8fdf5b06629
export RUN7_TEAM="$RUN7_ATTEMPT/aar_teams/honesty-sycophancy-concealing-gemma4_31b-opus48-run7-storage-continuation-1750282"

# Newly evaluated continuation scores; this starts empty and grows over time.
find "$RUN7_TEAM/scores" -maxdepth 1 -type f -name '*.json' -printf '%TY-%Tm-%Td %TH:%TM:%TS %f\n' | sort

# Retained and newly published findings, newest last.
find "$RUN7_TEAM/forum" -maxdepth 1 -type f -name '*.json' -printf '%TY-%Tm-%Td %TH:%TM:%TS %f\n' | sort

# Per-chain progress and live Slurm state.
tail -n 80 "$RUN7_TEAM/logs"/AGENT_LOG_gemma4_31b_explore_*.md
squeue -j 1750344,1750345,1750346,1750347,1750348,1750349,1750350,1750351,1750352,1750353
```

The exact 14-entry reconstructed pre-continuation history is also preserved
separately at:

```text
/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/full_attempts/20261007T203258Z-a8fdf5b06629/aar_teams/run7-recovered-history/forum
```

The passing one-iteration canary and its verification proof are retained at:

```text
/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/canary_attempts/20261007T183515Z-a8fdf5b06629
/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/canary_attempts/20261007T183515Z-a8fdf5b06629/metadata/canary_passed.json
```

The old `/checkpoint/ram/aar/winnieyangwn/honesty-sycophancy-concealing-gemma4_31b-vllm-v0`
path is not the source of truth for new results.

If only the evaluator pool must be replaced after an external deployment
snapshot disappears, preserve the attempt and its terminal failure artifacts,
then launch the committed recovery path with the exact attempt directory:

```bash
bash experiments/dishonest_sycophancy_concealing/run_7/submit_eval_recovery.sh \
  /checkpoint/ram/aar/$USER/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run7_attempts/<attempt-id>
```

The recovery validates the pinned worker snapshot hash and launches five new
four-GPU evaluators against the existing shared queue. It does not retry or
overwrite terminal candidate failures; research chains must use fresh run IDs.

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
