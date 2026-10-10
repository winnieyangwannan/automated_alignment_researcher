# Run 10 five-chain lifecycle check

- Status: blocked on a passed one-chain lifecycle proof
- Created: 2026-10-10 22:21 UTC
- Last updated: 2026-10-10 22:21 UTC
- Time standard: UTC

## Goal

Recorded: 2026-10-10 22:21 UTC

Prove Run 10's real five-chain concurrency and queue topology with the smallest
end-to-end workload before the full five-chain, 50-session-per-chain launch.
Each chain gets one Kimi session, one generated-method GPU step, and one
two-item evaluation. This is an operational proof, not a scientific run.

## Prerequisite

Recorded: 2026-10-10 22:21 UTC

The one-chain lifecycle check must have a fail-closed `passed` proof. The launch
wrapper supplies that exact proof to the shared engine; the five-chain proof
records its SHA-256 so the gate sequence cannot be bypassed or confused.

## Configuration and launch

Recorded: 2026-10-10 22:21 UTC

[`config/run.yaml`](config/run.yaml) declares five named chains, one research
session per chain, five concurrent one-step training jobs, five one-GPU
on-demand evaluators, and exactly two `verbalized_ece` items per adapter.

After the one-chain check passes, launch from the HPC `multi_kimi` worktree:

```bash
experiments/dishonest_sycophancy_concealing/run_10/canary/five_chain_lifecycle_check/launch/launch.sh \
  <one-chain-attempt>/metadata/canary_passed.json
```

## Plan

Recorded: 2026-10-10 22:21 UTC

1. Validate and retain the exact one-chain proof.
2. Start exactly five Kimi chains with one session each and no idle evaluator.
3. Require five source-bound proposal approvals, five atomic training receipts,
   and five successful one-step GPU adapter validations.
4. Publish one verified two-item suite, stage all five exact adapters, and start
   five one-GPU evaluator workers on demand.
5. Require five successful scores with `n: 2` and five matching findings.
6. Emit a five-chain lifecycle proof bound to the prerequisite proof.
7. Permit the full 5×50 launch only after both lifecycle proofs pass.

## Pass and stop criteria

Recorded: 2026-10-10 22:21 UTC

Pass requires all five independent lifecycles and exact child-job counts. Any
missing proposal, receipt, GPU proof, score, finding, evaluator marker, or
active orchestration incident is a no-go. A failure stops this gate; it does
not consume full-run sessions and does not authorize the 5×50 launch.

Operational events belong in [`PROGRESS.md`](PROGRESS.md). Evidence remains in
the immutable attempt under `/checkpoint`.
