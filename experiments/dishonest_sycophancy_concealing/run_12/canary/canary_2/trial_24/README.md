# Run 12 Canary 2 Trial 24

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-12 12:48 PT
- Last updated: 2026-10-12 12:48 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 12:48 PT

Run one fresh Kimi Canary 2 lifecycle with Trial 23's exact model and lifecycle
settings after correcting the duplicate `clarify_design` ownership path. Verify
that the lifecycle coordinator alone owns delegated clarification, then verify
the already-shared proposal, workspace-bootstrap, and approval paths.

## Context

Recorded: 2026-10-12 12:48 PT

Trial 23 successfully approved the proposal and registered workspace
`ws_f6d710158ed04ab5924a2ffe435f76f9`, but failed at
`clarify_design`. The coordinator leased action
`act_0ccaeac074c619914ada0f00`; outer Kimi then wrote a legacy result and
attempted native begin and complete operations for the same action. Research
stalled without a native completion receipt. Grounding approval, baseline
approval, production, and training did not begin, and no HTTP 429 occurred.

Trial 24 preserves every Trial 23 model, deployment, budget, data, and
lifecycle setting. Its only configuration change is the fresh run ID
`run12-canary2-trial24`.

## Launch

Recorded: 2026-10-12 12:48 PT

Not launched. The focused ownership correction is committed as `f210df8`; the
exact model-role mapping is covered by the operator's standing approval. After
exact-commit synchronization and config validation:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_24/submit_canary.sh
```

## Plan

Recorded: 2026-10-12 12:48 PT

1. Create fresh state and preserve all Trial 23 evidence.
2. Let outer Kimi author the method and submit its semantic proposal through
   the existing shared proposal tool.
3. Let shared host code journal the proposal and bootstrap/register the
   workspace exactly once.
4. Coordinate `clarify_design` with the isolated Kimi worker while withholding
   legacy action-result and native begin/complete authority from outer Kimi.
5. Route `approve_grounding` and `approve_baseline` through the existing
   trusted approval bridge while Kimi waits without a model turn.
6. Leave pipeline authoring and meta-optimization on their Trial 23 paths.
7. Continue through production and verified one-step training smoke, then stop.

## Model and execution roles

Recorded: 2026-10-12 12:48 PT

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

Recorded: 2026-10-12 12:48 PT

- One alpha chain; concurrency 8.
- Native AutoData commit `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Recipe `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Disjoint 64/32/32 meta partitions; minimum 3, maximum 10, patience 3.
- Production: 1,250 tasks to exactly 1,000 accepted rows.
- Campaign ceiling `$44,448`; stop after verified training smoke.
- Coordinator flags and all model/deployment settings are identical to Trial
  23. Grounding authoring, pipeline, analysis, mutation, and training-smoke
  coordinators remain explicitly disabled.

## Pass criteria

Recorded: 2026-10-12 12:48 PT

- One proposal is approved, journaled, and bound to exactly one registered
  workspace through the shared proposal/bootstrap implementation.
- `clarify_design` completes exactly once through the coordinator and isolated
  worker; outer Kimi receives no legacy action-result instruction, lease, or
  native completion authority for that action.
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

Recorded: 2026-10-12 12:48 PT

Stop and preserve evidence on duplicate proposal/workspace/action creation,
any second owner or legacy result for coordinated `clarify_design`, missing or
mismatched proposal/bootstrap/approval records, direct Kimi native completion
of a delegated action, binding or digest drift, coordinator stall, invalid
winner, unattainable production yield, training failure, or evaluator activity.
Never repair an active attempt.

## After a pass

Recorded: 2026-10-12 12:48 PT

Retain source/configuration hashes, proposal journal and workspace binding,
clarification and approval audits, coordinator/native receipts, winner proof,
production handoff, training receipt, job IDs, and phase timings.
