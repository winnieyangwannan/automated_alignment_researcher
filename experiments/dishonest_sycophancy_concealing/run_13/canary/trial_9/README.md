# Run 13 Canary Trial 9: sanitized identity-envelope rerun

**Experiment code branch:** `autodata`

- Status: prepared; not launched
- Created: 2026-10-12 12:49 PT
- Last updated: 2026-10-12 12:49 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Rerun the exact narrow Trial 8 live-proof gate after forwarding
`AAR_RUN13_TRIAL_ID` through the sanitized research-chain environment. Prove
the already-implemented secure typed initial `author_grounding`, exact
action-ID receipt recovery, and typed confirm-only `author_pipeline` behavior.
Stop after authoritative AutoData state advances beyond `author_pipeline`.

## Context

Trial 8 stopped at coordinator identity validation because the positive Slurm
environment allowlist omitted `AAR_RUN13_TRIAL_ID`. Commit
`e65e7e9e8405a65faa482e679c94912912d5cb2c` adds that single required field and
a regression contract covering all required coordinator variables. Trial 8
created a fresh revision-0 workspace but began no actions and produced no
receipts, so it proved none of the intended lifecycle corrections.

Trial 9 changes no lifecycle semantics. Its only behavioral difference from
Trial 8 is the repaired sanitized environment envelope.

## Launch

Launch from the matching isolated HPC checkout:

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=e65e7e9e8405a65faa482e679c94912912d5cb2c \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial9-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-provider-and-target-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_9/submit_canary.sh
```

The YAML retains the supported `training_smoke` terminal contract. This
diagnostic is manually stopped after the post-`author_pipeline` state is
durably verified, before substantive meta-optimization, production, training,
or evaluation.

## Plan

1. Verify the recovery manifest and create a fresh Trial 9 workspace.
2. Confirm the chain receives and validates the Trial 9 identity envelope.
3. Complete typed `clarify_design` and secure typed initial
   `author_grounding`.
4. Complete trusted `approve_grounding` and typed `author_pipeline`.
5. Verify all exact action-ID receipts and authoritative subsequent state.
6. Stop the diagnostic without exercising another lifecycle slice.

## Model and execution roles

- AAR researcher and monitor: Claude Opus 4.8.
- AutoData semantic researcher and generator: Claude Opus 4.8.
- AutoData row judge and configured evaluation judge: GPT-5.6 Luna.
- Target and training base: Gemma 4 31B IT.
- Evaluator: disabled and must not launch.
- AutoData revision: `51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`.
- Generation concurrency: `8`; per-request attempts: `3`.

## Pass criteria

Retained evidence must show the Trial 9 identity reached the chain; a fresh
workspace; completed typed clarify, grounding, and pipeline actions; exact
action-ID receipts that coexist without ambiguity; no lease in model-visible
transcripts; no unexpected workspace mutation; and authoritative advancement
beyond `author_pipeline`. No evaluator, production export, or optimizer step is
required for this narrow gate.

## Stop criteria

Stop on missing identity, reused native state, duplicate action begin, missing
durable lease, stale semantic output, unexpected mutation, receipt ambiguity,
failed native verification, or evaluator launch. On success, cancel only after
the post-`author_pipeline` evidence is durable.

## After a pass

Review the retained receipts and transcript boundary before deciding whether
the next unresolved action needs another typed coordinator slice.
