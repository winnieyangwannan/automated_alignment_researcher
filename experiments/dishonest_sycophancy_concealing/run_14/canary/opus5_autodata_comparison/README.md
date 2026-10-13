# Run 14 Opus 5 AutoData comparison

- Status: prepared; not launchable; not launched
- Created: 2026-10-12 23:46 PT
- Last updated: 2026-10-12 23:46 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Run the complete one-chain AutoData lifecycle through the verified
`training_smoke` receipt and compare Opus 5 with Opus 4.8 on the exact mutable
challenge-strategy loop specified by Run 13 Canary Trial 14.

## Context

Recorded: 2026-10-12 23:46 PT

The reference is
`experiments/dishonest_sycophancy_concealing/run_13/canary/trial_14`. Run 14
preserves its recipe, mutable-file boundary, ten-iteration schedule, task
counts, concurrency, retries, row judge, Gemma target/training base, production
contract, budget, and training-smoke stop boundary.

The only scientific treatment is:

- AAR researcher/monitor: Claude Opus 4.8 → Claude Opus 5.
- AutoData semantic optimizer and generator/challenger: Claude Opus 4.8 →
  Claude Opus 5.

Run identity and configuration paths necessarily differ for isolated
provenance; the parity test treats those as administrative differences, not
experimental treatments.

## Launch

Recorded: 2026-10-12 23:46 PT

This component is intentionally not launchable yet. The current Run 13
entrypoint and scheduled payloads hard-code the Run 13 identity, Trial 14
recovery scope, and Opus 4.8 model checks. A Run 14 launcher must extend those
fences explicitly and pass focused tests before this section gains an operator
command.

Required pre-launch order:

1. Implement and review the Run 14-specific runtime path without weakening Run
   13's guards.
2. Run the exact Claude CLI and Model API Opus 5 preflights.
3. Present the complete model-role map and resolved configuration revision for
   explicit user confirmation.
4. Synchronize the confirmed source commit to the matching HPC `autodata`
   worktree through direct Git-over-SSH.
5. Launch only after separate authorization.

## Plan

Recorded: 2026-10-12 23:46 PT

1. Prove declarative parity with the Run 13 Trial 14 reference.
2. Add fail-closed Run 14 runtime enablement and immutable attempt metadata.
3. Execute one `alpha` chain from the reviewed pre-AutoData boundary through a
   fresh AutoData workspace, ten native meta iterations, production, and one
   real-GPU training step.
4. Stop before evaluation and compare held-out-safe process/outcome metrics
   against the Opus 4.8 reference.

Monitor candidate `generation_strategy.json` diffs; per-iteration quality,
challenge, validity, and balanced utility; first-attempt versus final-corpus
challenge and validity; pressure-rewrite frequency, diversity, and conversion;
preserved fact/request/answer hashes; and final test evidence. Do not expose
hidden item-level evidence.

## Pass criteria

Recorded: 2026-10-12 23:46 PT

- Resolved configuration parity permits only the two requested model changes
  plus isolated Run 14 identity/profile paths.
- Native meta-optimization runs all ten iterations and records every candidate
  decision.
- Final test evidence satisfies quality, challenge, and validity constraints.
- Production exports 1,000 independently accepted rows from 1,250 fresh tasks
  with authenticated provenance.
- AAR produces a verified one-optimizer-step Gemma training receipt and a
  loadable PEFT adapter from the real export.
- No evaluator job launches and no hidden evidence becomes research-readable.

## Stop criteria

Recorded: 2026-10-12 23:46 PT

Stop before launch on an unreviewed parity difference, ambiguous or
unavailable model identity, absent explicit model-role confirmation, stale
source, or a bypass of Run 13/Run 14 identity fences.

Stop during execution on any identity, immutable-artifact, budget, approval,
provenance, export, or training-contract violation; any mutation outside
`recipe/generation_strategy.json`; any pressure rewrite that changes preserved
components; hidden-evidence leakage; or evaluator launch.

## After a pass

Recorded: 2026-10-12 23:46 PT

Retain the source-bound lifecycle proof and held-out-safe comparison record.
Report whether Opus 5 improved final quality, challenge, validity, and balanced
utility and whether it improved pressure-rewrite conversion or diversity.
Describe the result as one bounded canary, not a definitive model ranking.
