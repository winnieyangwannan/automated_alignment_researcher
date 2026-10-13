# Run 13 Canary Trial 12: bounded finalization hardening

**Experiment code branch:** `autodata`

- Status: failed closed before meta baseline generation
- Created: 2026-10-12 16:53 PT
- Last updated: 2026-10-12 17:18 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Rerun the complete Run 13 AutoData lifecycle from the preserved pre-AutoData
proposal and reach the verified `training_smoke` receipt. Exercise five bounded
provider-request attempts and one additional retained-result finalization pass.

## Context

Trial 11 live-proved all workspace actions, both delegated approvals, three
meta-optimization iterations, and early stopping. Its final full-corpus rerun
ended `final_incomplete`: the first pass saw repeated Luna HTTP 429 responses,
and the retry received one unusable Opus generator response. AutoData retained
95 successful task results and five accepted generated items.

Trial 12 changes only the observed failure boundaries:

- provider-request attempts increase from three to five;
- final full-corpus evaluation permits two retries instead of one while
  retaining the strongest digest-verified result for every task;
- unusable generator content receives a bounded, content-free diagnostic code.

It does not add provider-specific concurrency control or a generator-content
retry loop.

## Launch

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-trial12-commit> \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial12-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-provider-and-target-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_12/submit_canary.sh
```

The recovery manifest restores only the reviewed AAR proposal boundary. Trial
12 creates a fresh AutoData workspace and reruns the native lifecycle.

## Plan

1. Import the reviewed proposal into a fresh Trial 12 team.
2. Reconcile all native workspace actions with the existing typed coordinator.
3. Complete three to ten native meta-optimization iterations.
4. Finalize with at most three full-corpus passes, retaining prior successes.
5. Run production generation and publish the verified dataset handoff.
6. Consume the handoff in Gemma training and stop after one optimizer step.

## Model and execution roles

- AAR researcher and approval monitor: Claude Opus 4.8 through
  `meta-claude-cli-opus-4-8`.
- AutoData semantic researcher and generator: Claude Opus 4.8; generator route
  `meta-model-api-claude-4-8-opus` through Model API Responses.
- AutoData row judge and configured evaluation judge: GPT-5.6 Luna through
  Model API Responses.
- Target probe and training base: fixed Gemma 4 31B IT deployment, then the
  same base for the one-step training smoke.
- Delegated approvals: trusted host coordinator; host code signs native actions.
- Native orchestration, broker, comparator, receipts, and immutable-file checks:
  deterministic trusted code.
- Evaluator inference model and evaluator judge: disabled; no evaluator job may
  launch.
- AutoData revision: `f53bc2136905461ffdbba0a203a12e351e184aaf`, a focused
  child of the reviewed `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1` pin.
- Generation concurrency: `8`; per-request attempts: `5`.
- Campaign ceiling: `$62,000`; live reconciliation showed this was below the
  exact `$64,523.1552` ten-iteration bound. Trial 13 corrects it to `$65,000`.

## Monitoring goal and status template

Legend: ✓ live-proven, △ implemented/tested but not live-proven, ✗ not reached.

```text
AAR research and method proposal
  ✓ literature/method recovery
  ✓ method validation and proposal approval
             │
             ▼
AutoData workspace
  ✓ create/register fresh workspace
  ✓ clarify_design — typed coordinator
  ✓ author_grounding — secure typed coordinator
  ✓ approve_grounding — coordinator-owned signed approval
  ✓ author_pipeline — typed coordinator
             │
             ▼
Workspace finalization
  ✓ post-pipeline reconciliation
  ✓ authoring dry run
  ✓ approve_baseline — coordinator remained alive and completed it
  ○ approve_resources — not required in Trial 11
  ✓ freeze workspace and create meta execution
             │
             ▼
Meta-optimization
  ✓ baseline generation
  ✓ analyze_results — three actions completed
  ✓ mutate_candidate — three actions completed
  △ final full-corpus verification
      Three retained-result passes are implemented and unit-tested.
  ✗ finalize and export winning pipeline
             │
             ▼
Production
  ✗ create/run production execution
  ✗ generate 1,250 fresh tasks
  ✗ retain 1,000 accepted rows
  ✗ publish verified dataset handoff
             │
             ▼
Gemma training
  △ training-smoke coordinator implemented/tested
  ✗ consume production export
  ✗ perform one optimizer step
  ✗ verify receipt and adapter
             │
             ▼
Stop at training_smoke
  ✗ not reached
  ○ evaluator disabled
```

## Pass criteria

Require authenticated native receipts for all workspace and execution actions,
a verified winning-pipeline export, a production dataset handoff satisfying the
configured row and coverage requirements, and a `training_smoke` receipt proving
that Gemma consumed that exact export and completed one optimizer step. No
evaluator job may launch.

## Stop criteria

Stop on stale action/revision/digest, protected-file mutation, approval ownership
violation, exhausted bounded retries, unmet finalization or production policy,
unverified export identity, failed Gemma consumption, or any evaluator launch.

## After a pass

Preserve the immutable lifecycle, export, and training receipts. Do not scale
beyond this one-chain canary without reviewing the complete evidence bundle.
