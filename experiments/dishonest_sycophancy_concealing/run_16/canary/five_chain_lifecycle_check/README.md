# Run 16 five-chain native-generation lifecycle check

- Status: planned; blocked on the Run 16 one-chain proof
- Created: 2026-10-11 01:49 PT
- Last updated: 2026-10-11 01:49 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 01:49 PT

Prove five parallel Claude Opus 4.8 research chains and their shared training/evaluation
queues with the same bounded native-generation lifecycle used by the one-chain
gate. This is a topology proof, not a scientific result.

## Context

Recorded: 2026-10-11 01:49 PT

This is the ordered gate between the one-chain lifecycle check and the full
Run 16 experiment. It consumes and retains the exact passed one-chain proof;
its own proof records the prerequisite file's SHA-256.

No Run 16 prerequisite proof exists yet. Earlier canaries are retained as
historical evidence, but this fresh researcher configuration requires proofs
produced by the final Run 16 source revision.

## Launch

Recorded: 2026-10-11 01:49 PT

After synchronizing the final clean source revision, confirming the model-role
mapping, and obtaining the Run 16 one-chain proof, launch from the HPC
`autodata` worktree with that exact proof:

```bash
experiments/dishonest_sycophancy_concealing/run_16/canary/five_chain_lifecycle_check/launch/launch.sh \
  <one-chain-attempt>/metadata/canary_passed.json
```

After all five lifecycles finish, create the fail-closed proof:

```bash
python experiments/dishonest_sycophancy_concealing/run_16/canary/verify_run_16_canary.py \
  <five-chain-attempt>
```

## Plan

Recorded: 2026-10-11 01:49 PT

1. Validate the supplied one-chain proof and source ancestry.
2. Start `alpha`, `beta`, `gamma`, `delta`, and `epsilon` together in one
   isolated team, with one research session per chain.
3. Require five proposal-approved, source-bound, real-GPU one-step adapters.
4. Stage all five verified adapters, then start the same single one-GPU
   evaluator used by the one-chain gate to drain the shared queue.
5. Require five two-item `verbalized_ece` scores and five matching findings.
6. Emit a five-chain proof bound to the exact one-chain proof.

## Model and execution roles

Recorded: 2026-10-11 01:49 PT

The role mapping is identical to the one-chain gate: Claude Opus 4.8 model
`claude-opus-4-8` at maximum effort authors the methods and native training data;
`claude-4-8-opus` through Meta Model API reviews proposals; Gemma 4 31B IT is
the fixed training base and the vLLM evaluator base plus each promoted adapter.
`verbalized_ece` is rule-scored, so no evaluator-judge model is used. AutoData
has no generator, probe, judge, broker, workspace, comparator, or export role.

## Pass criteria

Recorded: 2026-10-11 01:49 PT

- The prerequisite is a passed one-chain proof from an ancestor commit.
- Exactly five distinct research-chain jobs and five real-GPU smoke proofs
  exist for the five configured seeds.
- All five exact adapters produce a two-item score and one matching finding.
- The evaluator records the required vLLM 0.25.1, language-model-only, and
  merged-checkpoint markers for every candidate.
- The final proof binds the prerequisite SHA-256 and confirms
  `data_generation.backend=native` / `AAR_AUTODATA=0`.

## Stop criteria

Recorded: 2026-10-11 01:49 PT

Stop on a missing or stale prerequisite proof, any AutoData initialization,
wrong child count, proposal or smoke failure, adapter mismatch, evaluator
failure, or missing score/finding pair.

## After a pass

Recorded: 2026-10-11 01:49 PT

Review and retain the held-out-safe proof. Only then may the full five-chain
Run 16 launcher be authorized; neither canary score is a scientific result.
