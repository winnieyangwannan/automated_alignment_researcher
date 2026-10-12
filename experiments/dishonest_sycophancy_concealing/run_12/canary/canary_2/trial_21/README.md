# Run 12 Canary 2 Trial 21

**Experiment code branch:** `autodata`

- Status: launch approved; preflight pending
- Created: 2026-10-12 03:17 PT
- Last updated: 2026-10-12 03:17 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 03:17 PT

Run one fresh normal Kimi Canary 2 lifecycle and verify that the trusted
coordinator waits for durable workspace registration before invoking the
isolated Kimi `clarify_design` worker. Continue through verified production and
one-step training smoke if all lifecycle gates remain healthy.

## Context

Recorded: 2026-10-12 03:17 PT

Trial 20 failed before `clarify_design`: native state appeared 13 seconds before
the lifecycle control registration, and the coordinator treated the absent
control file as `durable_record_invalid`. Commit `23023b1` changes only that
boundary: absent pre-registration control state now means “wait.” Trial 21
otherwise preserves Trial 20's confirmed models, recipe, budgets, and topology.

## Launch

Recorded: 2026-10-12 03:17 PT

After exact-commit synchronization and HPC validation:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_21/submit_canary.sh
```

## Plan

Recorded: 2026-10-12 03:17 PT

1. Create fresh state; never reuse Trial 20's failed workspace.
2. Run the normal outer Kimi research and proposal flow.
3. Verify the supervisor remains healthy while native state exists without a
   lifecycle control registration.
4. Coordinate exactly one native `clarify_design` action with the isolated
   tool-free Kimi worker.
5. Return later semantic actions to the established lifecycle configuration and
   continue through meta-optimization, production, and training smoke.
6. Stop before evaluation.

## Model and execution roles

Recorded: 2026-10-12 03:17 PT

- Outer AAR researcher: Kimi-K2.6 through `aar_8-kimi26` using Kimi Code.
- `clarify_design` worker: isolated one-turn Kimi-K2.6 through
  `aar_8-kimi26`, with no tools, workspace, lease, or lifecycle capability.
- Generator/teacher: Kimi-K2.6 through `autodata_8-kimi26`.
- Target probe and training base: fixed Gemma 4 31B deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Meta Model API.
- Proposal monitor, supervisor, broker, comparator, validity gate, leases,
  approvals, and receipts: deterministic trusted code from pinned sources.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.

## Configuration and invariants

Recorded: 2026-10-12 03:17 PT

- One alpha chain; concurrency 8.
- Pinned native AutoData commit: `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Recipe: `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Disjoint partitions: 64 tuning, 32 validation, 32 held-out tasks.
- Meta-optimization: minimum 3, maximum 10, patience 3.
- Production: 1,250 tasks to exactly 1,000 accepted rows.
- Campaign ceiling: `$44,448`.
- Stop after verified one-step training smoke; evaluator disabled.

## Pass criteria

Recorded: 2026-10-12 03:17 PT

- The missing pre-registration control file is treated as a wait state.
- Native `clarify_design` begins once, the protected lease never enters Kimi,
  and the typed outcome is bound to the action ID, revision, and digest.
- AutoData records its authoritative receipt and advances from clarification.
- A held-out-valid winner produces exactly 1,000 accepted production rows and
  a verified one-step training-smoke receipt.
- No evaluator activity occurs.

## Stop criteria

Recorded: 2026-10-12 03:17 PT

Stop and preserve evidence on model drift, repeated native action begin,
coordinator failure, lifecycle stall, invalid winner, mathematically
unattainable production yield, training-smoke failure, or evaluator activity.
Never repair or resume an active Trial 21 attempt.

## After a pass

Recorded: 2026-10-12 03:17 PT

Retain source/configuration hashes, endpoint preflight, coordinator and native
receipts, action-attempt count, winner validity proof, production handoff,
training receipt, job IDs, and phase timings.
