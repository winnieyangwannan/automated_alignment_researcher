# Run 14 one-chain native-generation lifecycle check

- Status: planned; not launched
- Created: 2026-10-10 17:02 PT
- Last updated: 2026-10-10 17:02 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-10 17:02 PT

Prove one complete Kimi research → native data generation → proposal approval →
real-GPU one-step training → two-item evaluation → finding lifecycle without
loading or producing any AutoData component or artifact.

## Plan

Recorded: 2026-10-10 17:02 PT

Launch one `canary` seed with one research session, a one-step PEFT training
job, and one one-GPU evaluator for exactly two `verbalized_ece` items.

## Pass criteria

Recorded: 2026-10-10 17:02 PT

- The resolved configuration records `data_generation.backend=native` and
  `AAR_AUTODATA=0`.
- The generated method has declared data provenance and passes proposal review.
- A non-empty loadable adapter, one score, and one matching result finding exist
  for the same run ID.
- No AutoData plugin, broker, workspace, state database, recipe execution, or
  production export exists in the attempt.

## Stop criteria

Recorded: 2026-10-10 17:02 PT

Stop on any AutoData initialization, missing provenance, method-contract
failure, invalid adapter, evaluator failure, or score/finding mismatch.

## After a pass

Recorded: 2026-10-10 17:02 PT

Review and record the held-out-safe evidence, then authorize the full five-chain
launcher. Do not treat the bounded score as a scientific conclusion.
