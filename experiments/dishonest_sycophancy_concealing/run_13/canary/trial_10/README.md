# Run 13 Canary Trial 10: trusted delegated-approval ownership

**Experiment code branch:** `autodata`

- Status: prepared; not launched
- Created: 2026-10-12 14:24 PT
- Last updated: 2026-10-12 14:24 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Live-prove that the existing trusted lifecycle supervisor, rather than the AAR
researcher turn, owns and completes `approve_grounding` and `approve_baseline`.
The gate passes when the exact `approve_baseline` action has a verified signed
audit and AutoData authoritatively advances beyond it.

## Context

Trial 9 live-proved the secure typed authoring path and then waited at
`approve_baseline` after the AAR Claude turn had ended. Trial 10 makes the
smallest ownership correction: it enables the existing delegated-approval
reconciler and fences Claude's duplicate approval MCP route. It adds no new
lifecycle state machine, approval policy, or AutoData transition.

All authoring behavior remains confirm-only. Approval decisions may still be
`approve` or `revise` according to immutable evidence and configured policy.

## Launch

Launch from the matching isolated HPC checkout:

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-trial10-commit> \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial10-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-provider-and-target-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_10/submit_canary.sh
```

The YAML retains the supported `training_smoke` terminal contract. Operational
monitoring stops this narrow diagnostic after the verified post-
`approve_baseline` transition, before substantive meta-optimization.

## Plan

1. Import only the reviewed pre-AutoData proposal into a fresh Trial 10 team.
2. Re-prove the typed clarify, grounding, and pipeline route.
3. Verify Claude cannot call `review_autodata_action` in coordinator-owned mode.
4. Verify the trusted supervisor completes `approve_grounding` with a signed audit.
5. Verify the same supervisor remains alive after the Claude turn and completes
   the exact `approve_baseline` action.
6. Stop after authoritative AutoData state advances beyond that action.

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
  ✓ create/register fresh workspace
  ✓ clarify_design — typed coordinator
  ✓ author_grounding — secure typed coordinator
  △ approve_grounding — coordinator-owned signed approval
      Existing bridge is tested; exclusive supervisor ownership is not live-proven.
  ✓ author_pipeline — typed coordinator
             │
             ▼
Workspace finalization
  ✓ post-pipeline reconciliation
  △ authoring dry run and approve_baseline
      Trial 10 must prove completion after the AAR Claude turn ends.
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

Retained evidence must show a fresh workspace; completed typed authoring
actions; no researcher-side approval tool execution; signed mode-600 audits
bound to the exact `approve_grounding` and `approve_baseline` action IDs,
workspace revisions, and artifact digests; native completion receipts; and
authoritative state beyond `approve_baseline`.

## Stop criteria

Stop on duplicate approval ownership, researcher approval-tool execution,
missing or unsafe audit, signature mismatch, stale action/revision/digest,
duplicate `action begin`, unsupported `approve_resources`, evaluator launch,
or any lifecycle transition not authenticated by AutoData.

## After a pass

Preserve the proof and decide whether to live-prove the already implemented
meta-optimization coordinators without expanding approval scope.
