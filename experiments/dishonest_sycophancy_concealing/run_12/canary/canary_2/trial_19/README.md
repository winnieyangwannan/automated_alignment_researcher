# Run 12 Canary 2 Trial 19

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-12 00:44 PT
- Last updated: 2026-10-12 00:44 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Repeat Trial 18 from a fresh workspace with one targeted correction: Kimi must
issue executable native tool calls for `clarify_design` instead of spending
continuation turns describing them. AAR requires the native begin, result write,
and complete checkpoints, while Kimi retains the scoped lease and decides
whether the already-reviewed workspace needs an edit. Zero workspace changes
remain valid.

## Context

Trial 18 reached an approved and registered workspace, but Kimi twice described
the correct native workflow without calling `action begin`. The generic
no-progress guard then failed the session. Trial 19 changes only the Kimi
adapter's `clarify_design` checkpoint enforcement. Later AutoData actions and
all scientific settings are unchanged.

The user granted standing launch approval for future trials using this exact
model and configuration profile. Reconfirmation is required if any listed model
or setting changes.

## Model and execution roles

- Researcher: Kimi-K2.6 through `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 through `autodata_8-kimi26`.
- Target probe and training base: fixed Gemma 4 31B through
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Model API.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.

## Configuration and invariants

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

- The pinned skill activation and ordinary checkpoint order remain valid.
- Kimi calls native `action begin`, writes valid `summary` and `decisions`, and
  calls native `action complete` with the same scoped lease.
- A no-edit confirmation is accepted when the reviewed workspace is complete;
  AutoData records the revision and advances to `author_grounding`.
- The unchanged lifecycle produces a held-out-valid winner, exactly 1,000
  accepted production rows, and a verified one-step training smoke.

## Stop criteria

Stop and preserve evidence if Kimi again emits prose instead of a required tool,
native `clarify_design` does not advance, any edit escapes its allowed path, a
new blocking error appears, source/model identity drifts, no held-out-valid
winner exists, production yield becomes mathematically insufficient, the
lifecycle stalls, or evaluator activity appears. Never repair or resume an
active Trial 19 attempt.

## Launch

After committing, synchronizing, and validating the exact source commit on the
matching HPC worktree, run:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_19/submit_canary.sh
```
