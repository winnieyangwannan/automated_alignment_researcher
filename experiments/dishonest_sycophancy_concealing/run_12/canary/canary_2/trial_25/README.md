# Run 12 Canary 2 Trial 25

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-12 14:27 PT
- Last updated: 2026-10-12 14:27 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 14:27 PT

Run one fresh Kimi Canary 2 lifecycle with Trial 24's exact model and lifecycle
settings after correcting the shared supervisor's proposal-identity envelope.
Live-prove `approve_grounding` through the existing shared signed approval path
while preserving Trial 24's proof that coordinated Kimi `clarify_design` has
exactly one owner and one native completion receipt.

## Context

Recorded: 2026-10-12 14:27 PT

Trial 24 successfully approved the proposal, registered a fresh workspace,
completed coordinated `clarify_design` exactly once while outer Kimi waited,
and completed legacy `author_grounding`. It then failed closed at
`approve_grounding`: the lifecycle supervisor entered the shared approval path
before the launcher-exported proposal identity was available in the
supervisor's environment. Native action `act_fc37f9b17969aaae1145e96d` recorded
`delegated_approval_failed`, and no approval receipt was written.

The corrective change is deliberately shared and narrow: make the existing
proposal identity available before starting the shared supervisor. It does not
change the approval implementation, Kimi prompts, Claude route, model roles,
budgets, data contract, coordinator flags, or downstream lifecycle behavior.
Trial 25 preserves every Trial 24 operational setting. Its only configuration
change is the fresh run ID `run12-canary2-trial25`.

## Launch

Recorded: 2026-10-12 14:27 PT

Not launched. After the focused supervisor identity-envelope correction and
this trial record are committed, synchronized by exact commit to the matching
HPC worktree, and validated, run:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_25/submit_canary.sh
```

## Plan

Recorded: 2026-10-12 14:27 PT

1. Create fresh state and preserve all Trial 24 evidence.
2. Let outer Kimi author the method and submit its semantic proposal through
   the existing shared proposal tool.
3. Let shared host code journal the proposal and bootstrap/register the
   workspace exactly once.
4. Coordinate `clarify_design` with the isolated Kimi worker while withholding
   legacy action-result and native begin/complete authority from outer Kimi.
5. Verify that the shared supervisor starts with the proposal identity already
   in its immutable process environment.
6. Route `approve_grounding` and `approve_baseline` through the existing shared
   trusted approval bridge while Kimi waits without a model turn.
7. Leave pipeline authoring and meta-optimization on their Trial 24 paths.
8. Continue through production and verified one-step training smoke, then stop.

## Model and execution roles

Recorded: 2026-10-12 14:27 PT

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

Recorded: 2026-10-12 14:27 PT

- One alpha chain; concurrency 8.
- Native AutoData commit `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Recipe `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Disjoint 64/32/32 meta partitions; minimum 3, maximum 10, patience 3.
- Production: 1,250 tasks to exactly 1,000 accepted rows.
- Campaign ceiling `$44,448`; stop after verified training smoke.
- Coordinator flags and all model/deployment settings are identical to Trial
  24. Grounding authoring, pipeline, analysis, mutation, and training-smoke
  coordinators remain explicitly disabled.

## Pass criteria

Recorded: 2026-10-12 14:27 PT

- One proposal is approved, journaled, and bound to exactly one registered
  workspace through the shared proposal/bootstrap implementation.
- `clarify_design` again completes exactly once through the coordinator and
  isolated Kimi worker; outer Kimi receives no legacy action-result
  instruction, lease, or native completion authority for that action.
- The supervisor's identity envelope is available before its first lifecycle
  action, and `approve_grounding` completes exactly once through the unchanged
  shared signed approval implementation with matching authoritative
  native/audit records.
- `approve_baseline` completes exactly once through the same shared approval
  bridge and publishes matching authoritative native/audit records.
- Kimi receives no lease or native completion authority for either coordinated
  approval.
- Native revision, digest, receipt, and resulting phase reconcile without
  prescribing the next phase.
- A held-out-valid winner produces exactly 1,000 accepted rows and a verified
  one-step training-smoke receipt; no evaluator activity occurs.

## Stop criteria

Recorded: 2026-10-12 14:27 PT

Stop and preserve evidence on duplicate proposal/workspace/action creation,
any second owner or legacy result for coordinated `clarify_design`, missing or
mismatched proposal/bootstrap/approval records, unavailable or drifting
supervisor identity, direct Kimi native completion of a delegated action,
binding or digest drift, coordinator stall, invalid winner, unattainable
production yield, training failure, or evaluator activity. Never repair an
active attempt.

## After a pass

Recorded: 2026-10-12 14:27 PT

Retain source/configuration hashes, proposal journal and workspace binding,
supervisor identity-envelope proof, clarification and approval audits,
coordinator/native receipts, winner proof, production handoff, training
receipt, job IDs, and phase timings.
