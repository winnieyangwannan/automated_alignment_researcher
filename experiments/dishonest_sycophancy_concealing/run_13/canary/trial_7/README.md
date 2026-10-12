# Run 13 Canary Trial 7: typed `author_pipeline` coordination

**Experiment code branch:** `autodata`

- Status: stopped after typed `author_pipeline`; receipt recovery failed
- Created: 2026-10-12 10:41 PT
- Last updated: 2026-10-12 12:10 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 10:41 PT

Run the Run 13 canary from a fresh pre-AutoData boundary and verify that the
trusted lifecycle supervisor retains ownership at `pipeline_pending` by
dispatching the native `author_pipeline` action through a narrow typed
coordinator. Continue through verified production and exactly one Gemma
optimizer step, then stop at `training_smoke` without evaluation.

## Context

Recorded: 2026-10-12 10:41 PT

Trial 6 exposed the next lifecycle ownership gap. AutoData remained the
authoritative state machine and reported `pipeline_pending` with
`author_pipeline` as the next scoped action, but the AAR supervisor did not yet
have an allowlisted typed handler that could claim and complete that action.
Trial 6 therefore did not establish supervisor ownership across this boundary.

Trial 7 requires the minimal backend-neutral, confirm-only `author_pipeline`
slice. The coordinator must acquire and durably retain the native lease, give a
semantic worker only a typed action context, validate its typed confirmation,
verify that the reviewed pipeline remained unchanged, complete the action
through AutoData, and verify the authoritative receipt and resulting state. It
must reconcile around AutoData's state machine rather than duplicate phase
logic in AAR. If the staged pipeline needs an edit, this first slice fails
closed; it does not let the worker write files.

While native state remains at the `author_pipeline` window, a Trial-7-only
trusted Claude tool fence denies the concurrent legacy researcher access to
`Bash`, `Write`, and `Edit`. This prevents it from racing the coordinator for
the lease. The retry controller reconstructs the same typed-lifecycle ownership
envelope before every sanitized retry submission.

As in Trial 6, recovery may reuse only hash-verified pre-AutoData AAR artifacts.
The attempt, team, proposal binding, AutoData workspace, actions, executions,
production data, and training state must all be fresh. The external recovery
manifest remains host-only and must not enter Git, the source snapshot, the
research-child environment, or a model prompt.

## Launch

Recorded: 2026-10-12 10:41 PT

Do not launch until the typed `author_pipeline` coordinator commit and explicit
shared-launcher Trial 7 support are reviewed. The wrapper also requires an
external recovery manifest owned by the launching user with mode `0600`.

After those gates pass and the exact model mapping is reconfirmed, launch from
the matching isolated HPC checkout:

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-full-git-sha> \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial7-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-run13-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_7/submit_canary.sh
```

This command is documentation, not launch authorization. No Trial 7 attempt or
job exists.

## Plan

Recorded: 2026-10-12 10:41 PT

1. Verify the external recovery manifest and create a fresh Trial 7 team.
2. Recreate the method-contract and approved-proposal receipts, then bootstrap
   a fresh AutoData workspace immediately before its first native action.
3. Reconcile the already supported typed actions without repeating native
   `action begin` operations.
4. At `pipeline_pending`, dispatch `author_pipeline` through only the reviewed
   typed coordinator and validate the bound confirmation and unchanged input.
5. Verify native completion, receipt bindings, revision/digest agreement, and
   the resulting phase exactly as AutoData returns it.
6. Continue the native lifecycle through the verified 1,000-row export and one
   Gemma optimizer step.
7. Stop at `training_smoke`; do not publish a holdout or start an evaluator.

## Lifecycle

```text
AAR Claude researcher
→ loads the autodata:autodata plugin skill
→ calls the native AutoData CLI
→ authors and freezes a workspace
→ meta-optimizes the permitted generation strategy
→ runs production generation
→ exports a verified dataset
→ AAR consumes that export for Gemma training
→ stops after one optimizer step
```

The model proposes semantic outcomes. Trusted host code owns approvals, leases,
state transitions, budgets, receipts, and immutable files. AutoData owns valid
actions and phase transitions. Only `generation_strategy.json` may change
during optimization, and the real pinned `autodata_pipelines` plugin remains
the implementation of record.

## Model and execution roles

- AAR researcher: Claude Opus 4.8 through
  `meta-claude-cli-opus-4-8`, maximum effort.
- AAR proposal monitor: Claude Opus 4.8 through Meta Model API.
- AutoData semantic researcher: Claude Opus 4.8 through the typed worker
  interface, including the allowlisted `author_pipeline` outcome.
- AutoData generator: `claude-4-8-opus` through
  `meta-model-api-claude-4-8-opus`, using `model_api_responses`.
- AutoData row judge: `gpt-5-6-luna` through Meta Model API.
- Target probe and training base: Gemma 4 31B IT.
- Evaluation judge: GPT-5.6 Luna, configured but not invoked.
- Evaluator inference: disabled.
- Lifecycle reconciliation, action leases, result validation, budgets,
  receipts, and immutable-file enforcement: deterministic trusted host code.

AutoData remains pinned to
`51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`. Concurrency is 8 and each model
request permits three attempts.

## Pass criteria

Recorded: 2026-10-12 10:41 PT

Trial 7 passes only if retained machine-readable evidence shows:

- all recovered inputs matched their hashes and no prior AutoData or downstream
  state was imported;
- the attempt, team, proposal binding, workspace, actions, and executions were
  fresh;
- the supervisor retained ownership at `pipeline_pending` and completed exactly
  one native `author_pipeline` action through the typed coordinator;
- the semantic outcome was bound to the expected action ID, input revision,
  and digest without exposing the lease, tools, or filesystem to the worker;
- the staged pipeline was unchanged by this confirm-only slice;
- the legacy researcher was fenced from mutation and lifecycle commands during
  the coordinator-owned pipeline window, including on any session retry;
- completion and the resulting native revision, digest, and phase matched
  authoritative AutoData state;
- production exported exactly 1,000 verified rows and Gemma consumed that
  export for exactly one optimizer step;
- the terminal boundary was `training_smoke`, with no evaluator, score,
  promotion, or later AAR iteration.

## Stop criteria

Recorded: 2026-10-12 10:41 PT

Stop before submission if the reviewed typed coordinator commit, explicit
Trial 7 launcher support, external manifest, AutoData pin, or confirmed model
mapping is missing. Stop during execution on reused native state, duplicate
`action begin`, missing durable lease, stale or malformed worker output, any
pipeline mutation during the action, phase prediction by AAR, failed
native receipt verification, more than one optimizer step, or any evaluator or
scoring process.

## After a pass

Recorded: 2026-10-12 10:41 PT

Retain the recovery verification/import receipts, fresh-state proof,
supervisor-ownership timeline, `author_pipeline` action and revision receipts,
resulting AutoData phase exactly as returned, production export receipt,
training-consumption receipt, and one-step adapter proof. Review them before
adding another typed action or enabling evaluation.
