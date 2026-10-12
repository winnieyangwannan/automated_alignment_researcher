# Run 13 Canary Trial 4: fresh AutoData recovery at `clarify_design`

**Experiment code branch:** `autodata`

- Status: prepared; launch blocked pending reviewed coordinator and recovery-import wiring
- Created: 2026-10-12 01:12 PT
- Last updated: 2026-10-12 01:12 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-12 01:12 PT

Reuse Trial 3's completed AAR literature/research, method, method-contract gate,
and approved proposal while creating entirely fresh AutoData state. The first
native semantic action must be `clarify_design`. Continue through native
meta-optimization, production, and one real-GPU Gemma optimizer step, then stop
at `training_smoke` without evaluation.

## Context

Recorded: 2026-10-12 01:12 PT

Trial 3 proved the AAR pre-AutoData path and reached native meta-optimization,
but the one-shot AAR Claude turn ended and the host tore down the lifecycle
supervisor. Trial 4 avoids repeating the slow pre-AutoData research stages and
tests the narrowly scoped, backend-neutral `clarify_design` coordinator.

The operator supplies an external, mode-0600 recovery manifest containing the
reviewed source paths, exact SHA-256 digests, and negative native identities.
It is snapshotted into host-owned attempt metadata and is never committed,
included in the source snapshot, exported to the research child, or placed in
a prompt. The source proposal receipt is verification-only because it embeds
old native identities. No Trial 3 AutoData state or downstream output may be
imported.

## Launch

Recorded: 2026-10-12 01:12 PT

Do not launch yet. The wrapper fails closed until the reviewed
`clarify_design` coordinator commit is an ancestor of the checkout and the
shared Run 13 launcher contains the reviewed pre-AutoData recovery-import seam.

After both gates pass, launch from the isolated HPC checkout:

```bash
AAR_RUN13_CLARIFY_COORDINATOR_COMMIT=<reviewed-full-git-sha> \
AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-manifest> \
AAR_RUN13_CANARY_ROOT=<reviewed-run13-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_4/submit_canary.sh
```

The wrapper selects this exact config and verifies the external manifest before
delegating to the shared Run 13 launcher. No launch has occurred from this
directory.

## Plan

Recorded: 2026-10-12 01:12 PT

1. Verify every source artifact against the external host-owned manifest.
2. Create a fresh Trial 4 attempt and team directory.
3. Import only the approved paper/proposal fields and byte-identical method.
4. Rerun the native method-contract validator and retain a Trial 4 proof bound
   to the imported method hash.
5. Reconcile the approved proposal into a fresh native AutoData workspace whose
   first native action is `clarify_design`.
6. Exercise only the allowlisted `clarify_design` coordinator slice; AutoData
   remains authoritative for the resulting phase and every later transition.
7. Continue through production and exactly one training optimizer step, then
   stop at `training_smoke`.

## Model and execution roles

- AAR researcher: Claude Opus 4.8 through
  `meta-claude-cli-opus-4-8`, maximum effort; its completed Trial 3 proposal is
  reused rather than rerun.
- AAR proposal monitor: Claude Opus 4.8 through Meta Model API; its exact
  approved Trial 3 decision is reused with digest verification.
- AutoData semantic researcher: Claude Opus 4.8 through the backend-neutral
  worker contract.
- AutoData generator: `claude-4-8-opus` through
  `meta-model-api-claude-4-8-opus`, using `model_api_responses`.
- AutoData row judge: `gpt-5-6-luna` through Meta Model API.
- Target probe and training base: fixed Gemma 4 31B IT checkpoint.
- Evaluation judge: GPT-5.6 Luna, not invoked because this canary stops at
  `training_smoke`.
- Evaluator inference model: not used.
- Approvals, leases, lifecycle reconciliation, budgets, receipts, and immutable
  file enforcement: trusted host code.

The pinned AutoData revision is
`51c18fdb0eaa69d8ad66a1805e9c08a507c5fbb1`. The runtime profile fixes
concurrency at 8 and model-request attempts at 3.

## Reuse boundary

The allowed reuse is limited to completed pre-AutoData AAR artifacts:

- the approved proposal paper, including its related-work/literature record;
- the byte-identical training method;
- the source execution-ready/method-contract evidence;
- the host-owned approved-proposal decision.

Trial 4 must not copy or resume Trial 3's AutoData workspace, revisions,
actions, leases, state database, meta execution, broker ledger/results,
production tasks/export, training state, scores, findings, checkpoints, or
adapters. The external manifest carries the reviewed negative identities;
observing any of them in Trial 4 is a stop condition.

## Pass criteria

Recorded: 2026-10-12 01:12 PT

The retained Trial 4 proof must show:

- every reused AAR source artifact matched its manifest SHA-256;
- a new attempt, team, AutoData state database, workspace, action IDs, and
  execution IDs were created;
- the first native action was `clarify_design`;
- the coordinator completed and verified that action without predicting the
  next phase;
- malformed semantic output, if encountered, did not repeat `action begin`;
- AutoData subsequently completed meta-optimization and a verified 1,000-row
  production export;
- Gemma training consumed that export and completed exactly one optimizer step;
- no evaluator, score, promotion, or later AAR research iteration started.

## Stop criteria

Recorded: 2026-10-12 01:12 PT

Stop before submission if either launch gate is missing, any source hash or
model role drifts, or the importer cannot produce a fresh Trial 4 method proof
and approved-proposal binding. Stop during execution if any forbidden Trial 3
AutoData identity or artifact appears, the first native action is not
`clarify_design`, the coordinator attempts an unsupported action, native
completion verification fails, production is incomplete, training smoke fails,
or evaluation starts.

## After a pass

Recorded: 2026-10-12 01:12 PT

Retain the source-artifact verification receipt, fresh-state proof, native
`clarify_design` action receipt, resulting AutoData phase exactly as returned,
production export receipt, training-consumption receipt, and one-step adapter
proof. Do not generalize the coordinator to later actions or launch evaluation
without separate review.
