# Run 12 Canary 2 Trial 22

**Experiment code branch:** `autodata`

- Status: launch approved; preflight pending
- Created: 2026-10-12 03:47 PT
- Last updated: 2026-10-12 03:47 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 03:47 PT

Run one fresh Kimi Canary 2 lifecycle and verify that the isolated Kimi
`clarify_design` worker can resolve its pinned deployment, return a typed
outcome, and allow native AutoData to advance through production and one-step
training smoke.

## Context

Recorded: 2026-10-12 03:47 PT

Trial 21 proved the registration-race repair but failed before the model call
because the worker omitted the non-secret Slurm deployment-registry locator.
Commit `f786f21` adds only `SLURM_CLUSTER_NAME` and the explicit
`V2_DEPLOYMENTS_ROOT` override to the worker allowlist. A live isolated-worker
call against the same deployment passed on HPC.

## Launch

Recorded: 2026-10-12 03:47 PT

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_22/submit_canary.sh
```

## Plan

Recorded: 2026-10-12 03:47 PT

1. Create fresh state and preserve all Trial 21 evidence.
2. Run outer Kimi research and proposal approval.
3. Coordinate `clarify_design` with one isolated, tool-free Kimi invocation.
4. Verify the native completion receipt and observed next phase.
5. Continue through meta-optimization, production, and training smoke.
6. Stop before evaluation.

## Model and execution roles

Recorded: 2026-10-12 03:47 PT

- Outer AAR researcher: Kimi-K2.6 via `aar_8-kimi26` and Kimi Code.
- `clarify_design` worker: isolated Kimi-K2.6 via `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 via `autodata_8-kimi26`.
- Target/training base: fixed Gemma 4 31B deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Meta Model API.
- Lifecycle, proposal monitor, broker, comparator, leases, approvals, and
  receipts: pinned deterministic AAR/AutoData code.
- Evaluator inference and evaluator judge: not used; evaluator disabled.

## Configuration and invariants

Recorded: 2026-10-12 03:47 PT

- One alpha chain; concurrency 8.
- Native AutoData commit `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Recipe `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Disjoint 64/32/32 meta partitions; minimum 3, maximum 10, patience 3.
- Production: 1,250 tasks to exactly 1,000 accepted rows.
- Campaign ceiling `$44,448`; stop after verified training smoke.

## Pass criteria

Recorded: 2026-10-12 03:47 PT

- `clarify_design` begins exactly once and the worker returns a correctly bound
  typed outcome without receiving tools, lease, or lifecycle authority.
- AutoData records its native completion receipt and advances.
- A held-out-valid winner produces exactly 1,000 accepted rows and a verified
  one-step training-smoke receipt.
- No evaluator activity occurs.

## Stop criteria

Recorded: 2026-10-12 03:47 PT

Stop and preserve evidence on deployment drift, coordinator failure, repeated
action begin, lifecycle stall, invalid winner, unattainable production yield,
training failure, or evaluator activity. Never repair an active attempt.

## After a pass

Recorded: 2026-10-12 03:47 PT

Retain source/configuration hashes, endpoint and isolated-worker proofs,
coordinator/native receipts, winner proof, production handoff, training receipt,
job IDs, and phase timings.
