# Run 12 Canary 2 Trial 16

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-11 22:28 PT
- Last updated: 2026-10-11 22:28 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 22:28 PT

Run one fresh AAR-to-AutoData-to-training-smoke lifecycle with the pinned
AutoData `autodata` skill available to every Kimi turn. Determine whether the
authoritative skill instructions prevent the no-op mutation behavior observed
in Canary 2 v2, without adding an SDK/ACP migration or another scientific
change.

## Context

Recorded: 2026-10-11 22:28 PT

Canary 2 v2 launched from AAR commit `65824ac1437c7e9a10fcab09ebdf20c49971f8c6`
and native AutoData commit `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
Its baseline completed, but Kimi proposed and completed three no-op mutations.
Each native candidate was rejected as `candidate made no harness change`, and
the rejected no-ops consumed the three-round patience window.

AAR correctly verified the pinned AutoData plugin for both agent backends, but
only Claude registered its published skill. The Kimi command did not include
the plugin's `skills/` directory. Trial 16 tests the smallest correction:
every initial and continued Kimi CLI invocation receives the verified pinned
directory through `--skills-dir`, and Kimi is told that the skill name is
`autodata` rather than Claude's qualified `autodata:autodata` name.

This trial deliberately does not migrate Kimi to SDK/ACP and does not add a
native no-op accounting change. If the same no-op recurs, stop and preserve the
evidence rather than layering another repair into the active attempt.

## Model and execution roles

Recorded: 2026-10-11 22:28 PT

- Researcher: Kimi-K2.6 through logical deployment `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 through logical deployment
  `autodata_8-kimi26`.
- Target probe and training base: fixed Gemma 4 31B through logical deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Model API.
- Proposal monitor, lifecycle supervisor, broker, comparator, orchestration,
  validity gate, yield monitor, and approvals: deterministic trusted code from
  pinned AAR and AutoData source snapshots.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.

These assignments are copied unchanged from the previously confirmed Canary 2
v2 contract. They must be presented for explicit confirmation again before
Trial 16 is launched.

## Launch

Recorded: 2026-10-11 22:28 PT

Trial 16 is prepared but not authorized for launch. Before submission, commit
the focused AAR change, synchronize the exact commit to the matching clean HPC
worktree, validate the pinned AutoData checkout at
`51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`, and obtain explicit confirmation
of the model mapping and unchanged lifecycle configuration.

After those gates pass, the only operator entrypoint is:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_16/submit_canary.sh
```

## Plan

Recorded: 2026-10-11 22:28 PT

1. Verify the Kimi command contains the pinned AutoData `skills/` directory on
   both its initial turn and every `--continue` turn.
2. Start one fresh lifecycle from AAR research/bootstrap; do not resume the
   failed Canary 2 v2 workspace or execution.
3. Confirm Kimi loads `autodata` before AutoData work and performs a real,
   evidence-backed candidate edit during `mutate_candidate`.
4. Continue through held-out-valid winner selection, production, and one-step
   training smoke only while all existing fail-closed gates remain healthy.

## Configuration and invariants

Recorded: 2026-10-11 22:28 PT

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

Recorded: 2026-10-11 22:28 PT

- The immutable launch proves the configured skill directory belongs to the
  same SHA-verified AutoData plugin used by the native wrapper.
- Kimi loads the `autodata` skill before performing AutoData work.
- Every accepted `mutate_candidate` action changes the allowed strategy and no
  candidate is rejected as `candidate made no harness change`.
- Meta-optimization selects a held-out-valid winner before production.
- Production retains exactly 1,000 accepted rows, and the verified handoff
  completes one real-GPU optimizer-step smoke.
- No evaluator launches and no unresolved code-health warning remains.

## Stop criteria

Recorded: 2026-10-11 22:28 PT

Stop and preserve evidence if the skill directory is absent or mismatched,
Kimi does not load `autodata`, a no-op mutation recurs, source/model identity
drifts, meta-optimization has no held-out-valid winner, production yield becomes
mathematically insufficient, the lifecycle stalls, or any evaluator activity
appears. Do not repair or resume the active Trial 16 attempt.

## After a pass

Recorded: 2026-10-11 22:28 PT

Retain the resolved skill path and plugin SHA, Kimi skill invocation evidence,
candidate lineage, held-out-validity proof, production-yield trajectory,
training handoff and smoke receipts, source/model identities, job IDs, and
phase timings. A pass validates this one-chain gate only.
