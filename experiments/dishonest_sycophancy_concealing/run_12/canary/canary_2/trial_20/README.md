# Run 12 Canary 2 Trial 20

**Experiment code branch:** `autodata`

- Status: launch approved; preflight in progress
- Created: 2026-10-12 02:41 PT
- Last updated: 2026-10-12 02:43 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 02:41 PT

Run one normal Kimi Canary 2 lifecycle from fresh state. The outer AAR researcher
is Kimi, and the trusted coordinator handles only native `clarify_design` by
invoking a separate one-turn, tool-free Kimi semantic worker. After that action,
the existing outer Kimi loop continues the unchanged lifecycle through verified
production and one-step training smoke.

## Context

Recorded: 2026-10-12 02:41 PT

Trial 18 showed that the legacy Kimi action loop could understand a no-edit
`clarify_design` decision but failed to issue native `action begin`. Trial 19 was
staged around stricter tool checkpoints but was not launched. Trial 20 supersedes
that prompt/tool-call approach with the backend-neutral coordinator already
proved with Claude in Run 13 Trial 4, now backed by an isolated Kimi worker.

“Isolated” describes the semantic worker's permissions, not a separate canary:
it receives the immutable action context, has no repository workspace, skills,
MCP tools, lifecycle capability, or lease, and returns one typed JSON outcome.
Trusted code validates the outcome and completes the native action.

## Launch

Recorded: 2026-10-12 02:41 PT

The exact model-role mapping was confirmed by the operator. After the focused
coordinator change is committed and synchronized to the matching HPC worktree,
run:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_20/submit_canary.sh
```

## Plan

Recorded: 2026-10-12 02:41 PT

1. Create one fresh alpha-chain attempt; never reuse Trial 18 or Trial 19 state.
2. Run the normal outer Kimi AAR research and proposal flow.
3. When native AutoData exposes `clarify_design`, let the supervisor acquire and
   persist its lease, invoke the isolated Kimi worker, validate the typed result,
   complete the action, and verify the native receipt and resulting state.
4. Return all later semantic actions to the existing outer Kimi lifecycle loop.
5. Continue through meta-optimization, a held-out-valid winner, production of
   exactly 1,000 accepted rows, and verified one-step training smoke.
6. Stop before evaluation.

## Model and execution roles

Recorded: 2026-10-12 02:41 PT

- Outer AAR researcher: Kimi-K2.6 through `aar_8-kimi26` using Kimi Code.
- `clarify_design` semantic worker: a separate one-turn Kimi-K2.6 invocation
  through `aar_8-kimi26`, with no tools, skills, workspace, lease, or lifecycle
  capability.
- Generator/teacher: Kimi-K2.6 through `autodata_8-kimi26`.
- Target probe and training base: fixed Gemma 4 31B through
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Meta Model API.
- Proposal monitor, lifecycle supervisor, broker, comparator, orchestration,
  validity gate, yield monitor, leases, approvals, and receipts: deterministic
  trusted code from pinned AAR and AutoData source snapshots.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.

## Configuration and invariants

Recorded: 2026-10-12 02:41 PT

- One fresh alpha chain; concurrency 8.
- Pinned native AutoData source:
  `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Recipe: `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Exact disjoint partitions: 64 tuning, 32 validation, 32 held-out test.
- Meta-optimization: minimum 3, maximum 10, patience 3.
- Production: 1,250 source tasks and exactly 1,000 accepted rows.
- Campaign ceiling: `$44,448`.
- Stop after verified one-step training smoke; evaluator disabled.
- Only `clarify_design` opts into the new coordinator in this trial.

## Pass criteria

Recorded: 2026-10-12 02:41 PT

- The outer researcher and the `clarify_design` worker are both Kimi-K2.6.
- Native `clarify_design` is begun exactly once and its protected lease never
  enters the Kimi prompt or subprocess environment.
- The worker returns a result bound to the exact action ID, input revision, and
  input digest; malformed results retry without repeating native `action begin`.
- A valid no-edit confirmation remains acceptable, and AutoData advances using
  its own native state transition and authoritative receipt.
- The normal Kimi lifecycle then produces a held-out-valid winner, exactly 1,000
  accepted production rows, and a verified one-step training-smoke receipt.
- No evaluator job, score, or finding is created.

## Stop criteria

Recorded: 2026-10-12 02:41 PT

Stop and preserve evidence if either Kimi role or deployment drifts; the worker
receives tools, skills, a repository workspace, lease, or lifecycle capability;
native `action begin` repeats; the outcome binding or receipt verification
fails; `clarify_design` does not advance; any later lifecycle action stalls; no
held-out-valid winner exists; production becomes mathematically unable to reach
1,000 rows; training smoke fails; or evaluator activity appears. Never repair
or resume an active Trial 20 attempt.

## After a pass

Recorded: 2026-10-12 02:41 PT

Retain the source and configuration hashes, Kimi endpoint preflight, coordinator
stage and native receipt, action-attempt count, resulting native phase, winner
validity proof, production handoff, training-consumption receipt, one-step
adapter proof, job IDs, and phase timings. A pass validates this one-chain
configuration only.
