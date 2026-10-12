# Run 12 Canary 2 Trial 18

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-12 00:01 PT
- Last updated: 2026-10-12 00:15 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 00:01 PT

Run one fresh lifecycle with one targeted parity change: for `clarify_design`,
let Kimi use the pinned AutoData skill and native CLI exactly as the Claude AAR
researcher does. Kimi inspects the action and workspace, begins the native
action, edits only if design intent is missing, and completes the action with
its scoped lease. A byte-identical workspace is valid when the reviewed design
is already complete.

## Context

Recorded: 2026-10-12 00:01 PT

Trial 17 passed pinned-skill activation, method authoring, proposal approval,
and workspace registration. Its first AutoData workspace edit succeeded, but
the separate result-file tool call was serialized as literal markup and the
research job failed closed as `required_checkpoint_missing`.

Trial 18 changes only this first AutoData action boundary. AAR no longer begins,
completes, or requires a mutation for `clarify_design`; it exposes the action to
Kimi's already-loaded pinned skill. Native AutoData retains the scoped lease,
allowed-path enforcement, result validation, audit revision, and state
transition. Later actions retain the existing trusted AAR bridge.

## Model and execution roles

Recorded: 2026-10-12 00:01 PT

- Researcher: Kimi-K2.6 through `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 through `autodata_8-kimi26`.
- Target probe and training base: fixed Gemma 4 31B through
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Model API.
- Proposal monitor, lifecycle supervisor, broker, comparator, and approvals:
  deterministic trusted code from the pinned AAR and AutoData snapshots.
- `clarify_design`: Kimi follows the pinned skill's native `status`, `action
  begin`, workspace inspection, and `action complete` flow; native AutoData
  validates and records the result.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.

## Launch

Recorded: 2026-10-12 00:01 PT

After the focused commit is synchronized to the clean matching HPC worktree,
the pinned native AutoData checkout is verified at
`51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`, and the unchanged model mapping is
explicitly confirmed, run:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_18/submit_canary.sh
```

## Plan

Recorded: 2026-10-12 00:01 PT

1. Start a fresh lifecycle; never resume Trial 17 state.
2. Require the pinned `autodata` skill activation before ordinary tools.
3. Verify Kimi begins and completes `clarify_design` through the native CLI.
4. Verify Kimi confirms the already-complete design without forcing a workspace
   edit, while native AutoData records the completion and advances.
5. Continue unchanged through grounding, pipeline authoring, meta-optimization,
   production, and one-step training smoke while existing gates remain healthy.

## Configuration and invariants

Recorded: 2026-10-12 00:01 PT

- One fresh alpha chain; concurrency 8.
- Pinned native AutoData and skill source:
  `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Recipe: `aar/autodata_recipes/dishonest_sycophancy_concealing_v2`.
- Exact disjoint partitions: 64 tuning, 32 validation, 32 held-out test.
- Meta-optimization: minimum 3, maximum 10, patience 3.
- Production: 1,250 source tasks and exactly 1,000 accepted rows.
- Campaign ceiling: `$44,448`.
- Stop after verified one-step training smoke; evaluator disabled.

## Pass criteria

Recorded: 2026-10-12 00:01 PT

- The pinned skill activation and ordinary checkpoint order remain valid.
- Kimi follows the native `clarify_design` action contract through the pinned
  skill and directly invokes native begin and complete with the scoped lease.
- A no-edit confirmation is accepted when the existing workspace already
  contains the reviewed intent; native AutoData records `summary` and
  `decisions` and advances the same action.
- AutoData advances to `author_grounding` and continues without a no-op mutation
  or lifecycle stall.
- A held-out-valid winner produces exactly 1,000 accepted production rows and a
  verified one-step training smoke; evaluator activity remains absent.

## Stop criteria

Recorded: 2026-10-12 00:01 PT

Stop and preserve evidence if skill activation regresses, Kimi does not use the
native begin/complete contract, it edits outside the allowed path, it calls a
workspace or execution step, native completion does not advance to
`author_grounding`, a no-op mutation recurs later in meta-optimization,
source/model identity drifts, no held-out-valid winner exists, production yield
becomes mathematically insufficient, the lifecycle stalls, or evaluator
activity appears. Never repair or resume the active Trial 18 attempt.

## After a pass

Recorded: 2026-10-12 00:01 PT

Retain the source-bound activation, native clarify action/revision evidence,
candidate lineage, winner validity, production-yield trajectory, training
handoff and smoke receipts, job IDs, and phase timings. A pass validates this
one-chain gate only.
