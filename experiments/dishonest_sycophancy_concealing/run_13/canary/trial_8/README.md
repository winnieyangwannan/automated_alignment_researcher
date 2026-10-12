# Run 13 Canary Trial 8: live proof of reviewed authoring fixes

**Experiment code branch:** `autodata`

- Status: prepared; not launched
- Created: 2026-10-12 12:24 PT
- Last updated: 2026-10-12 12:24 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Live-test only lifecycle behavior that is already implemented and locally
validated. In a fresh AutoData workspace, prove the secure typed initial
`author_grounding` path, exact action-ID receipt recovery after multiple
receipts coexist, and the typed confirm-only `author_pipeline` path. Stop the
diagnostic after authoritative AutoData state advances beyond
`author_pipeline`; do not implement or exercise a new semantic action slice.

## Context

Trial 7 proved `author_pipeline` itself, then failed because clarify recovery
counted receipts by workspace rather than exact action ID. Its legacy
`author_grounding` path also retained a lease token in a model transcript.
Commit `5044b353ccd96b1a72b765329eada2e17899a675` fixes exact receipt lookup and
adds a secure, confirm-only typed coordinator for the initial grounding
revision. Focused tests and integration against the exact detached AutoData
pin passed, but these two corrections have not yet been proven in a live run.

This trial makes no further lifecycle-behavior change. Trial 8 is mechanically
allowlisted in the existing Run 13 launch and authoring fences so it can replay
the reviewed Trial 7 contract under a fresh identity.

## Launch

Launch only from the matching isolated HPC checkout, with an external recovery
manifest owned by the launching user and mode `0600`:

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=5044b353ccd96b1a72b765329eada2e17899a675 \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial8-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-provider-and-target-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_8/submit_canary.sh
```

The committed configuration retains `stop_after: training_smoke` because that
is the supported Run 13 contract. Operationally, this diagnostic is manually
stopped as soon as retained authoritative evidence proves advancement beyond
`author_pipeline`, before substantive meta-optimization, production, or
training.

## Plan

1. Verify hash-bound pre-AutoData recovery inputs and create a fresh workspace.
2. Complete `clarify_design` through the existing typed coordinator.
3. Complete initial `author_grounding` through the secure typed coordinator,
   without exposing its native lease to the semantic worker or transcript.
4. Complete `approve_grounding` through the existing trusted approval path.
5. Complete the typed confirm-only `author_pipeline` action.
6. Verify exact action-ID receipts remain independently recoverable and that
   AutoData authoritatively reports the subsequent phase/action.
7. Stop the diagnostic before adding or exercising another coordinator slice.

## Model and execution roles

- AAR researcher and monitor: Claude Opus 4.8.
- AutoData semantic researcher and generator: Claude Opus 4.8.
- AutoData row judge and configured evaluation judge: GPT-5.6 Luna.
- Target and training base: Gemma 4 31B IT.
- Evaluator: disabled and must not launch.
- AutoData revision: `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Generation concurrency: `8`; per-request attempts: `3`.

## Pass criteria

Retained machine-readable evidence must show a fresh workspace and actions;
one completed typed `author_grounding` action with an unchanged reviewed
grounding document; no lease in model-visible transcripts; independently
verified clarify, grounding, and pipeline receipts bound to their exact action
IDs; one completed typed `author_pipeline` action with no pipeline mutation;
and authoritative advancement beyond `author_pipeline`. No evaluator, score,
production export, or optimizer step is required for this narrow gate.

## Stop criteria

Stop on reused native state, duplicate action begin, missing durable lease,
stale or malformed semantic output, any unexpected workspace mutation, receipt
ambiguity, failed native verification, or evaluator launch. On success, cancel
the diagnostic after the post-`author_pipeline` state is durably recorded.

## After a pass

Inspect the retained receipts and transcript redaction proof. Only then decide
whether the next unresolved native action needs another narrow typed slice.
