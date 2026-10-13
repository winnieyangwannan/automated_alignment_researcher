# Run 14 plan

Created: 2026-10-12 23:46 PT

Time standard: Pacific Time (`America/Los_Angeles`)

## Objective

Run a controlled Opus 5 versus Opus 4.8 comparison on the Run 13 Trial 14
mutable-challenge AutoData loop.

## Invariants

1. Change only the AAR researcher/monitor and AutoData generator/optimizer from
   Opus 4.8 to Opus 5, apart from required Run 14 identity and profile paths.
2. Preserve the recipe, target model, row judge, task counts, production
   contract, meta-optimization schedule, concurrency, retry policy, budgets,
   training-smoke boundary, storage policy, and evaluator-disabled behavior.
3. Keep the Run 13 Trial 14 result immutable as the Opus 4.8 reference.
4. Fail closed on unreviewed configuration drift, ambiguous model identity,
   missing proof, or isolation/provenance failure.

## Ordered gates

1. **Configuration parity — prepared.** Machine-readable tests allow only the
   requested model substitutions and necessary Run 14 identity/path changes.
2. **Runtime enablement — implemented and locally validated.** Run 14 owns its
   launcher and scheduled payloads; shared recovery and coordinator code has a
   narrow Run 14 allowlist covered by focused tests without weakening Run 13
   guards.
3. **Model preflight and confirmation — pending.** Validate the exact Opus 5
   CLI and Model API identities, then present the complete model-role mapping
   for explicit user confirmation.
4. **One-chain lifecycle canary — pending authorization.** Run through the
   verified production handoff and real-GPU one-step training receipt, then
   stop before evaluation.
5. **Comparison analysis — pending pass.** Compare process and final-test
   evidence with Run 13 Trial 14 without exposing hidden item-level evidence.

## Decision contract

A pass proves that the Opus 5 configuration completed the bounded lifecycle
under the same AutoData protocol. It does not by itself prove statistically
significant scientific superiority. Any conclusion that Opus 5 performs better
must identify the matched metrics, effect size, and limitations of a single
canary.
