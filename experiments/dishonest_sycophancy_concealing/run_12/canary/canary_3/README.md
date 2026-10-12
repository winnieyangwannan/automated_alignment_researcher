# Run 12 Canary 3: five-chain data-to-training topology

**Experiment code branch:** `autodata`

- Status: planned; documentation only; not launchable
- Created: 2026-10-11 18:52 PT
- Last updated: 2026-10-11 19:03 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 18:52 PT

Exercise five independent Canary 2-style data-to-training lifecycles in
parallel, one for each chain `alpha`, `beta`, `gamma`, `delta`, and `epsilon`.
Each chain uses its own isolated fixed Gemma target deployment and task
concurrency 2, for an aggregate maximum task concurrency of 10.
Every chain must independently complete exact three-iteration AutoData
meta-optimization, produce and verify 1,000 training rows, and pass one real-GPU
optimizer-step smoke before the gate can pass.

## Context

Recorded: 2026-10-11 18:52 PT

This is a planned topology and aggregate-load canary, not a scientific run.
It extends Canary 2 semantics from one chain to five parallel chains while
retaining the same per-chain data, training-smoke, and fail-closed boundaries.
Except for the confirmed five-chain topology and reduced concurrency, its
contract is identical to Canary 2 Trial 15.

No configuration or launcher exists yet. The shared bootstrap-canary path
currently rejects more than one seed. The current Canary 2 Trial 15 is the sole
predecessor gate: after it passes, this five-chain Canary 3 may be configured
and launched using source commit
`80479349b047de663853bf16f4a972cda93265c8`. There is no separate one-chain
Canary 3. This package records the intended contract without claiming that it
has been compiled, validated, synchronized, or launched.

The planned execution must include the committed strict Kimi server-enforced
JSON Schema fix in source commit
`80479349b047de663853bf16f4a972cda93265c8`. Its use by Canary 3 must be proven
by the future resolved configuration and retained runtime evidence; this
document is not that proof.

## Launch

Recorded: 2026-10-11 18:52 PT

Canary 3 is intentionally not launchable. Do not create or reconstruct an
ad-hoc submission command. Launch work is blocked until:

1. The current Canary 2 Trial 15 passes with durable evidence.
2. Trusted orchestration supports and validates exactly five bootstrap-canary
   seeds without weakening the one-chain path.
3. A checked-in config and thin launcher encode the contract below, pin source
   commit `80479349b047de663853bf16f4a972cda93265c8`, and pass
   focused local and HPC validation.
4. The exact model-and-role mapping is presented to and reconfirmed by the
   user for that configuration revision.

## Plan

Recorded: 2026-10-11 18:52 PT

1. Complete Canary 2 Trial 15 and retain its passing proof.
2. Add trusted five-seed bootstrap support and fail-closed per-chain evidence
   aggregation.
3. Create one validated configuration whose resolved snapshot binds source
   commit `80479349b047de663853bf16f4a972cda93265c8`, all five chains, and their
   independent lifecycle contracts.
4. Add a thin shared-launcher entrypoint; do not duplicate scheduler logic.
5. Run all five chains in parallel, continuously monitor aggregate provider and
   scheduler health, and stop the entire canary if any chain fails its gate.

## Model and execution roles

Recorded: 2026-10-11 18:52 PT

- Researcher: Kimi-K2.6 through logical deployment `aar_8-kimi26`, with one
  isolated research lifecycle per chain.
- Generator/teacher: Kimi-K2.6 through logical deployment
  `autodata_8-kimi26`, using strict server-enforced JSON Schema.
- Target probe and training base: five isolated fixed Gemma 4 31B deployments,
  exactly one dedicated deployment for each of `alpha`, `beta`, `gamma`,
  `delta`, and `epsilon`. The exact chain-to-logical-deployment IDs must be
  recorded and confirmed before launch.
- Row judge: Luna `gpt-5-6-luna` through Model API with the validated bounded
  transport-retry and structured-output contract used by Canary 2 successors.
- Proposal monitor, lifecycle supervisor, broker, comparator, orchestration,
  approvals, and five-chain evidence aggregation: deterministic trusted code
  from pinned AAR and AutoData source snapshots.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.

## Configuration and invariants

Recorded: 2026-10-11 18:52 PT

- Chains: exactly `alpha`, `beta`, `gamma`, `delta`, and `epsilon`, executing
  as five parallel and independently evidenced lifecycles.
- Per chain: exact meta-optimization minimum 3, maximum 3, patience 3.
- Per chain: exact disjoint partitions of 64 tuning, 32 validation, and 32
  held-out test tasks.
- Per chain: task concurrency 2; aggregate maximum task concurrency 10.
- Per chain: 1,250 production source tasks and exactly 1,000 retained rows.
- Per chain: one verified real-GPU optimizer-step training smoke consuming the
  contracted handoff and producing a non-empty loadable adapter.
- Global stop boundary: all five training smokes verified; evaluator disabled.
- All other provider, retry, JSON-schema, generation, budget, lifecycle, and
  training-smoke settings are identical to Canary 2 Trial 15, with the strict
  Kimi JSON-schema fix from commit
  `80479349b047de663853bf16f4a972cda93265c8` required.
- Per-chain isolation, identities, lineage, task partitions, artifacts,
  receipts, and completion markers must remain distinguishable and durable.
- Higher per-chain or aggregate concurrency is explicitly deferred until this
  five-chain topology gate passes.
- These are intended values only. No Canary 3 config has been validated.

## Pass criteria

Recorded: 2026-10-11 18:52 PT

Canary 3 passes only if all five chains pass. For every chain, durable evidence
must bind the resolved config and source revisions to exact `3/3/3`
meta-optimization, disjoint `64/32/32` partitions, its dedicated fixed Gemma
deployment, healthy concurrency-2 provider execution, an exact 1,250→1,000
production handoff, an exact data consumption receipt, one optimizer step, and
a non-empty loadable adapter.

The aggregate proof must identify all five per-chain evidence sets, demonstrate
that the chains ran with the intended parallel topology and aggregate maximum
concurrency 10, and confirm that no evaluator was allocated or launched. Four
passes and one failure is a failed Canary 3, not a partial pass.

## Stop criteria

Recorded: 2026-10-11 18:52 PT

Do not launch unless Canary 2 Trial 15 has passed. Also do not launch while
five-seed trusted orchestration, config, launcher, target deployment mapping,
pinning to source commit `80479349b047de663853bf16f4a972cda93265c8`, or
user model-role confirmation remains unvalidated. Once launched, stop and
preserve all evidence if any chain has an identity or partition mismatch,
lifecycle failure, terminal provider-health failure, no-progress loop, invalid
handoff, training-smoke failure, missing durable proof, or unexpected evaluator
activity. Never replace, restart, or silently exclude a failed chain to
manufacture a five-chain pass.

## After a pass

Recorded: 2026-10-11 18:52 PT

Retain the aggregate proof and each chain's resolved configuration, source and
model identities, job IDs, lifecycle timing, meta-optimization lineage,
production handoff, consumption receipt, training timing, adapter manifest,
and hashes. Review this evidence before deciding whether the topology and
aggregate provider load are suitable for a later full run. A canary pass does
not authorize evaluation or scientific promotion. Only after this gate passes
may a separate reviewed configuration propose higher concurrency.
