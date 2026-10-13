# Run 13 Canary Trial 13: capacity-corrected rerun

**Experiment code branch:** `autodata`

- Status: prepared; not launched
- Created: 2026-10-12 17:18 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Rerun the complete one-chain AutoData lifecycle from the preserved pre-AutoData
proposal and reach the verified `training_smoke` receipt. Preserve Trial 12's
five provider attempts and three retained-result finalization passes while
correcting only the fail-closed campaign reservation.

## Trial 12 evidence and correction

Trial 12 live-proved every workspace action, both delegated approvals, the
authoring dry run, baseline approval, and workspace freeze. It stopped before
meta baseline generation with `workspace_trusted_settings_invalid` because its
`$62,000` campaign ceiling was below the trusted ten-iteration bound.

The exact bound is `$64,523.1552` for 21,630 worst-case model-call
reservations, including authoring and finalization feedback. Trial 13 uses a
rounded `$65,000` fail-closed ceiling. This is a reservation bound, not an
expected-spend estimate. No provider, concurrency, retry, lifecycle, recipe,
or model setting changes.

## Launch

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-trial13-commit> \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial13-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-provider-and-target-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_13/submit_canary.sh
```

The recovery manifest restores only the reviewed AAR proposal boundary. Trial
13 creates a fresh AutoData workspace and reruns the native lifecycle.

## Fixed execution contract

- AAR researcher/monitor: Claude Opus 4.8.
- AutoData semantic worker/generator: Claude Opus 4.8.
- AutoData row judge: GPT-5.6 Luna.
- Target/training base: Gemma 4 31B IT.
- AutoData revision: `f53bc2136905461ffdbba0a203a12e351e184aaf`.
- Concurrency: `8`; provider attempts: `5`; three full-corpus passes.
- Meta iterations: minimum `3`, maximum `10`.
- Stop boundary: verified `training_smoke`; evaluator disabled.

## Monitoring goal

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
  ✓ approve_grounding — signed trusted approval
  ✓ author_pipeline — typed coordinator
             │
             ▼
Workspace finalization
  ✓ post-pipeline reconciliation and authoring dry run
  ✓ approve_baseline
  ○ approve_resources — conditional
  ✓ freeze workspace and create meta execution
             │
             ▼
Meta-optimization
  ✗ baseline generation
  △ analyze_results — implemented/tested
  △ mutate_candidate — implemented/tested
  △ three-pass final full-corpus verification
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
  ✗ consume the real production export
  ✗ perform one optimizer step
  ✗ verify consumption receipt and PEFT adapter
             │
             ▼
Stop at training_smoke
  ✗ not reached
  ○ evaluator intentionally disabled
```

## Pass and stop criteria

Pass only with authenticated native lifecycle/export receipts plus a verified
Gemma one-step training receipt and adapter. Stop on any identity, immutable
artifact, budget, approval, export, or training-contract violation, or if an
evaluator job launches.
