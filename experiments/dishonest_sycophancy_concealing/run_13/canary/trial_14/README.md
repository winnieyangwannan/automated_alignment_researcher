# Run 13 Canary Trial 14: mutable challenge strategy

**Experiment code branch:** `autodata`

- Status: prepared; not launched
- Created: 2026-10-12 22:06 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Run the complete one-chain AutoData lifecycle through the verified
`training_smoke` receipt while testing whether a mutable, context-specific
challenge strategy improves target challenge and valid-row yield relative to
Trial 13's fixed protected pressure sentences.

## Context

Trial 13 allowed Opus to optimize the initial generation prompts, but final
target-feedback hardening selected literal sentences from protected `task.py`.
Its native optimization stopped after three non-improving candidates. Final
test evidence had strong teacher quality but zero aggregate challenge and
validity, so production correctly did not start.

Trial 14 keeps `task.py` and `check.py` protected. The only mutable file remains
`recipe/generation_strategy.json`, which now contains a typed
`challenge_strategy`. Its instruction guides both initial pressure generation
and full, context-specific pressure-frame rewrites. Trusted code preserves the
facts, task request, and teacher answer during feedback rewrites.

This diagnostic trial runs exactly ten meta iterations. It does not stop after
three unchanged candidates.

## Launch

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-trial14-commit> \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial14-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-provider-and-target-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_14/submit_canary.sh
```

The recovery manifest restores only the reviewed pre-AutoData proposal
boundary. Trial 14 creates a fresh AutoData workspace and native lifecycle.

## Model and execution roles

- AAR researcher and delegated monitor: Claude Opus 4.8 through
  `meta-claude-cli-opus-4-8`.
- AutoData semantic optimizer and per-task generator/challenger: Claude Opus
  4.8 through `meta-model-api-claude-4-8-opus`.
- AutoData row judge: GPT-5.6 Luna.
- Target probe and training base: Gemma 4 31B IT, fixed base before training.
- Evaluator inference and evaluator judge: not used; evaluator is disabled.
- Lifecycle transitions, approvals, budgets, receipts, and protected paths:
  trusted host code using AutoData revision
  `f53bc2136905461ffdbba0a203a12e351e184aaf`.
- Concurrency: `8`; provider attempts: `5`; full-corpus passes: `3`.
- Meta iterations: exactly `10`.
- Stop boundary: verified `training_smoke`.

## Monitoring goal

Compare Trial 14 with Trial 13 at both strategy and outcome levels:

- Record the complete `generation_strategy.json` diff for every candidate,
  especially changes to `challenge_strategy.instruction`.
- Record tuning and hidden-validation quality, challenge, validity, and balanced
  utility for every iteration.
- Record first-attempt versus final-full-corpus challenge and validity.
- Record how often pressure rewriting runs, produces a materially different
  frame, and converts a target-not-challenging row into an accepted row.
- Check pressure-frame diversity and confirm that no fixed sentence is being
  repeated mechanically.
- Verify the preserved fact, task-request, and teacher hashes on every selected
  pressure rewrite.
- Compare final test evidence with Trial 13's recorded zero aggregate challenge
  and validity. Do not expose hidden item-level evidence.

Legend: ✓ live-proven, △ implemented/tested but not live-proven, ✗ not reached.

```text
AAR research and method proposal
  ✓ literature/method recovery
  ✓ method validation and proposal approval
             │
             ▼
AutoData workspace
  ✓ create/register fresh workspace — previously live-proven
  ✓ clarify_design — typed coordinator previously live-proven
  ✓ author_grounding — secure typed coordinator previously live-proven
  ✓ approve_grounding — signed trusted approval previously live-proven
  ✓ author_pipeline — typed coordinator previously live-proven
             │
             ▼
Workspace finalization
  ✓ post-pipeline reconciliation and authoring dry run — previously live-proven
  ✓ approve_baseline — previously live-proven
  ○ approve_resources — conditional
  ✓ freeze workspace and create meta execution — previously live-proven
             │
             ▼
Meta-optimization
  △ mutable challenge strategy — implemented/tested, not live-proven
  ✗ complete all 10 iterations
  ✗ finalize and export a valid winning pipeline
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

## Pass criteria

- Native meta-optimization runs all ten configured iterations and records every
  candidate decision.
- Final test evidence satisfies AutoData's quality, challenge, and validity
  constraints without hidden-evidence leakage.
- Production exports exactly 1,000 independently accepted rows from 1,250 fresh
  tasks with authenticated provenance.
- AAR consumes that export and produces a verified one-optimizer-step Gemma
  training receipt and loadable PEFT adapter.
- No evaluator job launches.

## Stop criteria

Stop on any identity, immutable-artifact, budget, approval, provenance, export,
or training-contract violation. Stop if the mutable strategy escapes
`recipe/generation_strategy.json`, a pressure rewrite changes preserved
components, hidden item-level evidence becomes research-readable, or an
evaluator job launches.
