# Run 12 Canary 2 Trial 6

**Experiment code branch:** `autodata`

- Status: prepared and launch-blocked pending the `HARNESS_PY` repair gates
- Created: 2026-10-11 01:59 PT
- Last updated: 2026-10-11 01:59 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 01:59 PT

Prove the complete bounded AutoData-to-training lifecycle after repairing the
two independent pre-child launcher failures exposed by Trial 5. Trial 6 must
complete exactly three meta-optimization iterations over disjoint `64/32/32`
partitions, produce and verify exactly 1,000 accepted rows from 1,250 source
tasks at concurrency 32, consume the complete handoff in one real optimizer
step, save a valid non-empty PEFT adapter, and stop before evaluation.

## Context

Recorded: 2026-10-11 01:59 PT

Trial 5 made no research or training progress. Its first launcher, job
`1812591`, failed closed when the shared HPC checkout advanced during the queue
wait. The resulting immutable per-attempt AAR and native AutoData snapshots
eliminated that race: the second attempt validated detached, exact, independent
source snapshots and their manifest before continuing.

The second Trial 5 launcher, job `1812713`, then failed before child submission.
The submitter had exported the valid shared runtime as `HARNESS_PY`, but
`replication/env_multidimensional.sh` unconditionally replaced it with
`${AAR_REPO}/.venv/bin/python`. In this execution `AAR_REPO` correctly referred
to the immutable, environment-free source snapshot, so the replacement path did
not exist. Trial 6 is the same confirmed experiment contract in a fresh run ID;
it remains blocked until that environment handoff is fixed and validated.

## Model and execution roles

Carried forward under the user's bounded replacement-trial authorization
confirmed at 2026-10-11 01:45 PT

| Role                                | Model or implementation            | Backend / identity                                 |
| ----------------------------------- | ---------------------------------- | -------------------------------------------------- |
| Researcher and visible host agent   | Kimi-K2.6                          | Kimi CLI; deployment `aar_8-kimi26`                |
| Data generator and teacher          | Kimi-K2.6                          | Local broker; deployment `autodata_8-kimi26`       |
| Proposal and semantic monitor       | Claude Opus 4.8                    | FAIR Model API; fail-closed                        |
| Baseline operational approval       | Deterministic trusted AAR policy   | Local signed approval bridge                       |
| Target probe and training base      | `gemma-4-31B-it`                   | Fixed checkpoint; vLLM 0.25.1 language-model-only  |
| Retained target deployment          | `gemma-4-31B-it`                   | `winnieyangwn-r12-alpha-i1-c0dab4f7`               |
| Row-quality and challenge judge     | `gpt-5-6-luna`                     | FAIR Model API                                     |
| AutoData orchestration/comparator   | Trusted deterministic native code  | Feedback-safe pinned AutoData revision             |
| Evaluator inference/evaluator judge | Not used                           | Trial stops after verified training smoke          |

The fixed target/training checkpoint is
`/checkpoint/ram/shared/models/google/gemma-4-31B-it`. Concurrency is `32`, the
campaign ceiling is `$5,500`, and the boundary is `training_smoke`. Any change
to these confirmed fields requires fresh user confirmation.

## Launch

Recorded: 2026-10-11 01:59 PT

Trial 6 is authorized but not yet launchable. After the `HARNESS_PY` repair is
committed, synchronized, and passes the focused HPC and live runtime gates, run
the committed wrapper from the Run 12 directory on `fair-cw-use2-1`:

```bash
AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7 \
  canary/canary_2/trial_6/submit_canary.sh
```

It must submit one `alpha` bootstrap-canary chain, reuse the retained target,
stop after `training_smoke`, and submit no evaluator. The command shown here is
an operator contract; this preparation did not execute it.

### Mandatory pre-launch gates

1. Preserve the caller-selected shared `HARNESS_PY` when execution source is an
   immutable snapshot without its own virtual environment.
2. Prove by regression test that sourcing every pipeline environment file keeps
   the shared interpreter and exact detached source root distinct.
3. Re-run the complete relevant feedback, immutable-snapshot, launcher, and
   runtime regression suites against the focused commit.
4. Fast-forward synchronize the exact committed AAR revision to a clean matching
   HPC worktree and pass the focused HPC suite.
5. Revalidate both immutable source revisions, the source-manifest digest,
   checkpoint, mode-600 secrets, exact Trial 6 configuration, and all three live
   model endpoints without exposing secret values.
6. Confirm that no evaluator is configured or submitted and that the stop
   boundary remains verified `training_smoke`.

## Plan

Recorded: 2026-10-11 01:59 PT

1. Complete and test the `HARNESS_PY` environment-handoff repair.
2. Commit only the focused repair and Trial 6 package.
3. Synchronize the exact commit and run the required HPC regression gates.
4. Launch Trial 6 automatically after the final runtime preflight.
5. Monitor every lifecycle transition through verified training smoke or a
   fail-closed stop, maintaining `PROGRESS.md` and `TIMINGS.md`.

## Pass criteria

Recorded: 2026-10-11 01:59 PT

Trial 6 passes only if:

1. Every pre-launch gate passes against the exact retained source revisions.
2. All queued and running jobs use the attempt-local immutable source snapshots
   while invoking the explicitly selected external architecture-compatible
   Python environment.
3. Freeze produces exactly one canonical registered execution with `3/3/3`,
   disjoint `64/32/32`, and valid grounding/holdout digests.
4. Native meta-optimization completes exactly three iterations and finalizes a
   provenance-bound winner without using held-out tasks.
5. Production attempts 1,250 fresh source tasks at c32 and publishes exactly
   1,000 accepted rows with at least 0.95 successful-task fraction.
6. The handoff and consumption receipt bind the same 1,000 rows and hashes; one
   optimizer step completes and a non-empty loadable PEFT adapter passes.
7. The attempt stops after training smoke with no evaluator, held-out scoring,
   publication, or promotion.

## Stop criteria

Recorded: 2026-10-11 01:59 PT

Stop and preserve evidence if any pre-launch gate is missing; source or runtime
identity drifts; the snapshot depends on a shared mutable checkout; the selected
interpreter is absent or overwritten; any exact execution, partition, budget,
provenance, feedback, registration, production, handoff, optimizer, adapter, or
loadability contract fails; an evaluator starts; or the user requests a stop.

## Monitoring

Record meaningful transitions in `PROGRESS.md` and durable intervals/counters
in `TIMINGS.md`. Monitoring is read-only and must not mutate the live attempt,
relax gates, expose generated content, or repair a running workspace in place.

## After a pass

Recorded: 2026-10-11 01:59 PT

Retain the adapter, dataset and consumption receipts, execution intents,
source/config pins, partition/holdout digests, feedback evidence, budget
accounting, and timing report. Do not evaluate or promote the adapter without a
separate explicit request.
