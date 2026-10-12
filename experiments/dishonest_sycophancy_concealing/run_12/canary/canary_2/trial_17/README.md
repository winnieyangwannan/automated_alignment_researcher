# Run 12 Canary 2 Trial 17

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-11 22:54 PT
- Last updated: 2026-10-11 22:54 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 22:54 PT

Run one fresh AAR-to-AutoData-to-training-smoke lifecycle after making Kimi's
first AutoData tool call a verified activation of the pinned `autodata` skill.
Test only whether that activation gate lets the existing lifecycle use the
authoritative skill instructions; do not add another scientific or lifecycle
change.

## Context

Recorded: 2026-10-11 22:54 PT

Trial 16 proved that `--skills-dir` made the pinned skill discoverable, but
availability alone did not activate it. Kimi entered the native action loop
without a `Skill` call and wrote `No edits needed`. Research job `1827982` and
its dependency-blocked controller `1827983` were cancelled before
meta-optimization, production, or training.

Trial 17 adds one AAR-side gate: while AutoData is enabled and a pinned skill
directory is configured, Kimi's first structured tool call must be
`Skill({"skill": "autodata"})`, and its matching tool result must report that
the skill loaded inline. Until that proof exists, the ordinary
`_continuation_prompt()` state machine cannot run. The activation marker is
excluded from lifecycle milestone accounting so literature discovery and all
later checkpoints retain their prior order.

## Model and execution roles

Recorded: 2026-10-11 22:54 PT

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

These assignments and all scientific settings are unchanged from the
previously confirmed Trial 16 contract. Explicit Trial 17 confirmation is
required before submission.

## Launch

Recorded: 2026-10-11 22:54 PT

Trial 17 is staged but not yet authorized for submission. Commit the focused
gate, synchronize that exact commit to the clean matching HPC worktree, verify
the pinned AutoData checkout at
`51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`, and obtain explicit confirmation
of the model mapping and unchanged lifecycle configuration.

The only operator entrypoint is:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_17/submit_canary.sh
```

## Plan

Recorded: 2026-10-11 22:54 PT

1. Require the first Kimi tool call to be `Skill` with the exact argument
   `autodata`; require its correlated success result before normal checkpoints.
2. Confirm literature discovery remains the first ordinary lifecycle milestone.
3. Start one fresh lifecycle; do not resume Trial 16's workspace or execution.
4. Continue through a real mutation, held-out-valid winner selection,
   production, and one-step training smoke only while existing gates remain
   healthy.

## Configuration and invariants

Recorded: 2026-10-11 22:54 PT

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

Recorded: 2026-10-11 22:54 PT

- The transcript's first structured tool call is exactly
  `Skill({"skill": "autodata"})`, followed by the correlated successful
  `loaded inline` tool result.
- `get_literature` remains the first ordinary lifecycle checkpoint.
- Every accepted `mutate_candidate` action changes the allowed strategy and no
  candidate is rejected as `candidate made no harness change`.
- Meta-optimization selects a held-out-valid winner before production.
- Production retains exactly 1,000 accepted rows, and the verified handoff
  completes one real-GPU optimizer-step smoke.
- No evaluator launches and no unresolved code-health warning remains.

## Stop criteria

Recorded: 2026-10-11 22:54 PT

Stop and preserve evidence if the exact skill activation or its success result
is absent, any ordinary tool precedes it, literature discovery is skipped, a
no-op mutation recurs, source/model identity drifts, meta-optimization has no
held-out-valid winner, production yield becomes mathematically insufficient,
the lifecycle stalls, or evaluator activity appears. Do not repair or resume
the active Trial 17 attempt.

## After a pass

Recorded: 2026-10-11 22:54 PT

Retain the source-bound skill invocation and result, candidate lineage,
held-out-validity proof, production-yield trajectory, training handoff and
smoke receipts, source/model identities, job IDs, and phase timings. A pass
validates this one-chain gate only.
