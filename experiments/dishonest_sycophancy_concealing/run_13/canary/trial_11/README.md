# Run 13 Canary Trial 11: delegated-approval ownership rerun

**Experiment code branch:** `autodata`

- Status: prepared; not launched
- Created: 2026-10-12 14:37 PT
- Last updated: 2026-10-12 14:37 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Rerun Trial 10 after extending the existing supervisor identity scope. Prove
that the trusted lifecycle supervisor exclusively owns and completes
`approve_grounding` and `approve_baseline`, including after the AAR Claude turn
ends.

## Context

Trial 10 failed before workspace creation because one supervisor scope check
still allowed only Trials 7–9. No native action began and no receipt was
created. Trial 11 changes no lifecycle behavior: it adds the fresh identity to
that existing fail-closed boundary and retains the Trial 10 approval fence.
The typed authoring actions remain confirm-only.

## Launch

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-trial11-commit> \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial11-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-provider-and-target-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_11/submit_canary.sh
```

The configured terminal remains `training_smoke`; this narrow diagnostic is
stopped after the verified post-`approve_baseline` transition.

## Plan

1. Import the reviewed proposal into a fresh Trial 11 team.
2. Re-prove typed clarification, grounding, and pipeline authoring.
3. Verify the Claude approval MCP route is fenced.
4. Verify signed coordinator-owned `approve_grounding`.
5. Verify coordinator-owned `approve_baseline` after the Claude turn ends.
6. Stop after AutoData authenticates the resulting state.

## Model and execution roles

- AAR researcher and approval monitor: Claude Opus 4.8.
- AutoData semantic researcher and generator: Claude Opus 4.8.
- AutoData row judge and configured evaluation judge: GPT-5.6 Luna.
- Target and training base: Gemma 4 31B IT.
- `approve_baseline`: deterministic trusted operational policy.
- Evaluator: disabled and must not launch.
- AutoData revision: `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Generation concurrency: `8`; per-request attempts: `3`.

## Monitoring goal and status template

Legend: ✓ live-proven, △ implemented/tested but not live-proven, ✗ not reached.

```text
AAR research and method proposal
  ✓ literature/method recovery
  ✓ method validation and proposal approval
             │
             ▼
AutoData workspace
  ✓ create/register fresh workspace — previously live-proven
  ✓ clarify_design — typed coordinator
  ✓ author_grounding — secure typed coordinator
  △ approve_grounding — coordinator-owned signed approval
  ✓ author_pipeline — typed coordinator
             │
             ▼
Workspace finalization
  ✓ post-pipeline reconciliation
  △ authoring dry run and approve_baseline
      Trial 11 must prove completion after the AAR Claude turn ends.
  ? approve_resources — conditional and intentionally unsupported by this gate
  ✓ freeze workspace and create meta execution — previously reached in Trial 4
             │
             ▼
Meta-optimization
  △ baseline generation — entered previously, never completed end-to-end
  △ analyze_results — typed coordinator implemented/tested
  △ mutate_candidate — typed coordinator implemented/tested
  ✗ complete the 3–10 iteration optimization loop
  ✗ finalize and export the winning pipeline
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

Require a fresh workspace, typed action receipts, no researcher-side approval
tool execution, protected signed audits bound to both exact approval actions,
native completion receipts, and authoritative state beyond `approve_baseline`.

## Stop criteria

Stop on duplicate ownership, approval-tool execution by Claude, missing or
unsafe audit, stale action/revision/digest, unsupported `approve_resources`,
unverified native transition, or evaluator launch.

## After a pass

Preserve the proof, then live-prove the already implemented meta-optimization
coordinators without expanding approval scope.
