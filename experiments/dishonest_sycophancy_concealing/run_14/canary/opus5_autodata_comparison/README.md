# Run 14 Opus 5 AutoData comparison

- Status: source launch path implemented and validated; not launched
- Created: 2026-10-12 23:46 PT
- Last updated: 2026-10-12 23:55 PT
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

From the synchronized HPC `autodata` worktree:

```bash
AAR_RUN14_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-run14-commit> \
AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-run14-manifest> \
AAR_RUN14_CANARY_ROOT=<reviewed-opus5-provider-and-target-proof-root> \
AAR_RUN14_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN14_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_14/canary/opus5_autodata_comparison/launch/launch.sh
```

The launcher fails closed unless the checkout is clean on branch `autodata`,
the reviewed commit is an ancestor, the external recovery manifest is an
owner-only regular file targeted to Run 14 Trial 14, the provider proof matches
the Opus 5 generator and chosen Gemma deployment, the pinned AutoData checkout
is exact and clean, and all resolved role identities and budgets match the
declarative configuration.

Required pre-launch order:

1. Review and commit this Run 14 runtime path.
2. Prepare the external Run 14 recovery manifest and Opus 5 provider proof.
3. Present the complete model-role map and resolved configuration revision for
   explicit user confirmation.
4. Synchronize that exact confirmed commit to the matching HPC `autodata`
   worktree through direct Git-over-SSH.
5. Launch only after separate authorization.

## Plan

Recorded: 2026-10-12 23:46 PT

1. Prove declarative parity with the Run 13 Trial 14 reference.
2. Use the fail-closed Run 14 runtime path and immutable attempt metadata.
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
