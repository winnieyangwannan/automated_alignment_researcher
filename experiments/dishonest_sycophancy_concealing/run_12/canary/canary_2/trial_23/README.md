# Run 12 Canary 2 Trial 23

**Experiment code branch:** `autodata`

- Status: failed; evidence preserved
- Created: 2026-10-12 12:04 PT
- Last updated: 2026-10-12 12:48 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 12:04 PT

Run one fresh Kimi Canary 2 lifecycle while moving only delegated grounding and
baseline approval triggering from Kimi's continuation prompt to the shared,
backend-neutral lifecycle coordinator. Verify the already-shared proposal and
workspace-bootstrap path at the same time.

## Context

Recorded: 2026-10-12 12:04 PT

The audit found no separate Kimi implementation for proposal review, workspace
bootstrap, or approval security. Claude and Kimi already call the same
`submit_idea_proposal` and `review_autodata_action` implementations. The narrow
remaining difference was scheduling: Kimi's continuation prompt decided when
to invoke the approval tool. Trial 23 makes the supervisor own that trigger for
`approve_grounding` and `approve_baseline` while reusing the existing trusted
approval implementation unchanged.

The attempt launched from source commit
`ccd83ed6ed0bb874fe978830c4872291c56613bd` and failed at
`clarify_design`. Proposal approval and workspace bootstrap succeeded, but the
coordinator and outer Kimi both tried to own action
`act_0ccaeac074c619914ada0f00`. No native completion receipt was created, and
grounding approval, baseline approval, production, and training did not begin.
This was an ownership collision, not a rate-limit failure; no HTTP 429 was
observed.

## Launch

Recorded: 2026-10-12 12:04 PT

Launched once and failed; do not relaunch this preserved attempt. The command
used was:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_23/submit_canary.sh
```

Use the separately staged Trial 24 folder for the next fresh attempt after the
ownership correction is committed, synchronized, and verified.

## Plan

Recorded: 2026-10-12 12:04 PT

1. Create fresh state and preserve all Trial 22 evidence.
2. Let outer Kimi author the method and submit its semantic proposal through
   the existing shared proposal tool.
3. Let shared host code journal the proposal and bootstrap/register the
   workspace exactly once.
4. Coordinate `clarify_design` with the existing isolated Kimi worker.
5. Let the supervisor route only `approve_grounding` and `approve_baseline`
   through the existing trusted approval bridge while Kimi waits without a
   model turn.
6. Leave pipeline authoring and meta-optimization on their Trial 22 paths.
7. Continue through production and verified one-step training smoke, then stop.

## Model and execution roles

Recorded: 2026-10-12 12:04 PT

- Outer AAR researcher: Kimi-K2.6 via `aar_8-kimi26` and Kimi Code.
- `clarify_design` worker: isolated Kimi-K2.6 via `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 via `autodata_8-kimi26`.
- Grounding integrity monitor: Claude Opus through the existing shared monitor.
- Baseline approval: existing deterministic operational policy; no model.
- Target/training base: fixed Gemma 4 31B deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Meta Model API.
- Lifecycle, proposal binding, broker, leases, approvals, and receipts: pinned
  deterministic AAR/AutoData code.
- Evaluator inference and evaluator judge: not used; evaluator disabled.

## Configuration and invariants

Recorded: 2026-10-12 12:04 PT

- One alpha chain; concurrency 8.
- Native AutoData commit `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Recipe `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Disjoint 64/32/32 meta partitions; minimum 3, maximum 10, patience 3.
- Production: 1,250 tasks to exactly 1,000 accepted rows.
- Campaign ceiling `$44,448`; stop after verified training smoke.
- The only newly enabled coordinator is approval. Grounding authoring,
  pipeline, analysis, mutation, and training-smoke coordinators remain
  explicitly disabled.

## Pass criteria

Recorded: 2026-10-12 12:04 PT

- One proposal is approved, journaled, and bound to exactly one registered
  workspace through the shared proposal/bootstrap implementation.
- `approve_grounding` and `approve_baseline` each complete exactly once through
  the shared approval bridge and publish matching authoritative native/audit
  records.
- Kimi receives no lease or native completion authority for the coordinated
  grounding and baseline approvals.
- Native revision, digest, receipt, and resulting phase reconcile without
  prescribing the next phase.
- A held-out-valid winner produces exactly 1,000 accepted rows and a verified
  one-step training-smoke receipt; no evaluator activity occurs.

## Stop criteria

Recorded: 2026-10-12 12:04 PT

Stop and preserve evidence on duplicate proposal/workspace/action creation,
missing or mismatched proposal/bootstrap/approval records, direct Kimi native
completion of either delegated approval, binding or digest drift, coordinator
stall, invalid winner, unattainable production yield, training failure, or
evaluator activity. Never repair an active attempt.

## After a pass

Recorded: 2026-10-12 12:04 PT

Retain source/configuration hashes, proposal journal and workspace binding,
approval audits, coordinator/native receipts, winner proof, production handoff,
training receipt, job IDs, and phase timings.
