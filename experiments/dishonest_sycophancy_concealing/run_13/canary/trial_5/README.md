# Run 13 Canary Trial 5: supervisor-owned AutoData optimization

**Experiment code branch:** `autodata`

- Status: planned; not launched
- Created: 2026-10-12 02:42 PT
- Last updated: 2026-10-12 02:52 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 02:42 PT

Start from a fresh pre-AutoData recovery boundary and prove that the trusted
lifecycle supervisor retains ownership after the original AAR Claude turn
returns. Reconciliation must continue through the backend-neutral
`analyze_results` and `mutate_candidate` action slices without treating
completion of one model turn as completion of the experiment. The configured
terminal boundary remains `training_smoke`; no evaluator may start.

## Context

Recorded: 2026-10-12 02:42 PT

Trial 5 reuses only reviewed pre-AutoData AAR artifacts through an external,
mode-0600 recovery manifest. It creates fresh attempt, team, proposal binding,
AutoData state, workspace, actions, executions, production data, and training
state. The manifest is operator-owned and must not enter Git, the immutable
source snapshot, research-child environment, or model prompt.

The lifecycle coordinator owns reconciliation from `baseline_pending` through
the repeated native `analyze_results → mutate_candidate` optimization cycle. A
tool-free worker returns a typed complete replacement for only
`recipe/generation_strategy.json`; trusted host code validates the binding,
writes that file atomically, completes the native action, and verifies its
receipt. AutoData continues to own all lifecycle transitions.

The remaining launch prerequisite is backend-neutral host ownership of the
verified production-handoff → training-submission → one-step-proof boundary.

## Launch

Recorded: 2026-10-12 02:42 PT

Do not launch yet. The Run 13 launcher supports Trial 5 recovery and the native
semantic action cycle is implemented, but the lifecycle owner does not yet
submit and verify training after the production handoff. The wrapper remains
fail-closed until that final host-owned boundary is reviewed and an external
owner-only mode-0600 Trial 5 recovery manifest is supplied.

After all gates are reviewed, launch from the matching isolated HPC checkout:

```bash
AAR_RUN13_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-full-git-sha> \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-trial5-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-run13-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_5/submit_canary.sh
```

This command is documentation, not launch authorization. No Trial 5 attempt or
job exists.

## Plan

Recorded: 2026-10-12 02:42 PT

1. Verify the external recovery manifest and every allowlisted source hash.
2. Create a fresh Trial 5 attempt and import only the approved proposal fields
   and byte-identical method into a fresh team.
3. Create fresh method-contract and approved-proposal receipts, then bootstrap
   a new AutoData workspace immediately before `clarify_design`.
4. Verify that the lifecycle supervisor remains the sole owner when the
   original AAR Claude turn returns.
5. Reconcile native state through every `analyze_results` and
   `mutate_candidate` pair using typed backend-neutral worker outcomes and
   native AutoData transitions.
6. Continue through verified production and a host-owned submission of exactly
   one Gemma optimizer step.
7. Stop at `training_smoke`; do not publish a holdout or start evaluation.

## Model and execution roles

- AAR researcher: Claude Opus 4.8 through
  `meta-claude-cli-opus-4-8`, maximum effort; the reviewed pre-AutoData proposal
  is recovered rather than regenerated.
- AAR proposal monitor: Claude Opus 4.8 through Meta Model API; the source
  approval is hash-verified and rebound to fresh Trial 5 receipts.
- AutoData semantic researcher: Claude Opus 4.8 through the backend-neutral
  semantic-worker interface.
- AutoData generator: `claude-4-8-opus` through
  `meta-model-api-claude-4-8-opus`, using `model_api_responses`.
- AutoData row judge: `gpt-5-6-luna` through Meta Model API.
- Target probe and training base: fixed Gemma 4 31B IT checkpoint.
- Evaluation judge: GPT-5.6 Luna, configured but not invoked because the canary
  stops at `training_smoke`.
- Evaluator inference model: not used; evaluator launch and holdout publication
  are disabled.
- Supervisor, action discovery, leases, retries, receipts, budgets, state
  transitions, and immutable-file enforcement: deterministic trusted host code.

AutoData remains pinned to
`51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`. Concurrency is 8 and each model
request permits three attempts.

## Pass criteria

Recorded: 2026-10-12 02:42 PT

Trial 5 passes only if retained machine-readable evidence shows:

- every recovered source artifact matched the external manifest and no prior
  AutoData or downstream state was imported;
- the attempt, team, proposal run, workspace, actions, and executions are fresh;
- the supervisor remained alive and authoritative after the original AAR Claude
  turn completed;
- native AutoData state advanced from `baseline_pending` through every
  receipt-verified `analyze_results` and `mutate_candidate` action without a
  duplicate `action begin`;
- each worker outcome was bound to the expected action ID, revision, and digest;
- only `recipe/generation_strategy.json` changed during optimization, and the
  run reached a verified 1,000-row production export plus exactly one Gemma
  optimizer step;
- the terminal boundary was `training_smoke`, with no evaluator job, score,
  promotion, or later AAR iteration.

Reaching the end of meta-optimization alone does not make Trial 5 a pass.

## Stop criteria

Recorded: 2026-10-12 02:42 PT

Stop before submission if the reviewed coordinator commit, external manifest,
model mapping, or host-owned training submission/verification is missing. Stop
during execution if any prior native identity or downstream artifact appears,
supervisor ownership ends with the AAR Claude turn, an action is begun twice, a
stale worker outcome is accepted, any file other than
`recipe/generation_strategy.json` changes during optimization, native receipt
verification fails, training exceeds one optimizer step, or any evaluator or
scoring process starts.

## After a pass

Recorded: 2026-10-12 02:42 PT

Retain the manifest-verification and import receipts, fresh-state proof,
supervisor-ownership timeline, action/revision receipts through every analysis
and mutation, resulting native phases exactly as returned, production export
receipt, training-consumption receipt, and one-step adapter proof. Review those
records before enabling evaluation.
