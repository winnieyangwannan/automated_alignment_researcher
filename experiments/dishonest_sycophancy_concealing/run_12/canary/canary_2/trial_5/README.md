# Run 12 Canary 2 Trial 5

**Experiment code branch:** `autodata`

- Status: prepared but launch-blocked pending comprehensive feedback repair,
  commit, synchronization, and complete HPC validation
- Created: 2026-10-11 01:01 PT
- Last updated: 2026-10-11 01:32 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 01:01 PT

Prove the complete bounded AutoData-to-training lifecycle after repairing the
non-actionable authoring feedback exposed by Trial 4. Trial 5 must complete
exactly three meta-optimization iterations over disjoint `64/32/32`
partitions, produce and verify exactly 1,000 accepted rows from 1,250 source
tasks at concurrency 32, consume the complete handoff in one real optimizer
step, save a valid non-empty PEFT adapter, and stop before evaluation.

## Context

Recorded: 2026-10-11 01:01 PT

Trial 4 proved the repaired trusted host FSM through proposal approval,
grounding approval, and pipeline authoring. It then repeated one invalid edit:
Kimi added unsupported `max_tokens` to `generation_strategy.json`, while the
broker reduced the protected checker's actionable error to `solve_failed`.
Eight identical failures consumed revisions without self-correction. The user
stopped Trial 4 at `pipeline_pending` revision 21; no baseline, execution,
production, training, or evaluation began.

Trial 5 is a fresh attempt. It must pin the native AutoData repair that passes
only framework-allowlisted, non-content-bearing checker codes while keeping raw
stderr, prompts, rows, responses, and secrets private. The AAR repair must also
provide safe bounded feedback at every Run 12 lifecycle boundary, terminate
repeated stable failures, and reconcile process markers with authoritative
Slurm state.

## Model and execution roles

Recorded and explicitly confirmed by the user: 2026-10-11 01:01 PT

| Role                                | Model or implementation            | Backend / identity                                      |
| ----------------------------------- | ---------------------------------- | ------------------------------------------------------- |
| Researcher and visible host agent   | Kimi-K2.6                          | Kimi CLI; deployment `aar_8-kimi26`                     |
| Data generator and teacher          | Kimi-K2.6                          | Local broker; deployment `autodata_8-kimi26`            |
| Proposal and semantic monitor       | Claude Opus 4.8                    | FAIR Model API; fail-closed                             |
| Baseline operational approval       | Deterministic trusted AAR policy   | Local signed approval bridge                            |
| Target probe and training base      | `gemma-4-31B-it`                   | Fixed checkpoint; vLLM 0.25.1 language-model-only      |
| Retained target deployment          | `gemma-4-31B-it`                   | `winnieyangwn-r12-alpha-i1-c0dab4f7`                    |
| Row-quality and challenge judge     | `gpt-5-6-luna`                     | FAIR Model API                                          |
| AutoData orchestration/comparator   | Trusted deterministic native code | Newly pinned feedback-safe AutoData revision            |
| Evaluator inference/evaluator judge | Not used                           | Trial stops after verified training smoke               |

The fixed target/training checkpoint is
`/checkpoint/ram/shared/models/google/gemma-4-31B-it`. Concurrency is `32`, the
campaign ceiling is `$5,500`, and the boundary is `training_smoke`. Any change
to these confirmed fields requires fresh user confirmation.

## Launch

Recorded: 2026-10-11 01:01 PT

**Do not launch yet.** After every gate below passes on the exact committed and
synchronized source, the user has authorized automatic launch without another
confirmation:

```bash
AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7 \
  canary/canary_2/trial_5/submit_canary.sh
```

Run the committed wrapper from the Run 12 directory on `fair-cw-use2-1`. It
must submit one `alpha` bootstrap-canary chain, reuse the retained target,
stop after `training_smoke`, and submit no evaluator.

### Mandatory pre-launch gates

1. Native AutoData is committed and pinned to the feedback-safe revision; its
   complete test suite passes.
2. Protected authoring checks emit only reviewed structured error codes, and
   local plus Firecracker brokers propagate the code without raw content.
3. Every Run 12 failure handoff returns a bounded safe cause or explicit
   redaction category/evidence pointer; generic-only and raw-exception paths
   found by the comprehensive audit are repaired and tested.
4. Repeated stable native authoring failures terminate after the configured
   bound rather than consuming the full revision budget.
5. External cancellation, internal watchdog failure, and authoritative Slurm
   terminal state remain distinct and reconcile to one durable marker.
6. The previously implemented exact execution, partition, budget, lifecycle,
   retry, idempotency, and training-submission contracts remain green.
7. Both repositories are committed, exact commits are fast-forward synchronized
   to clean matching HPC worktrees, and the full relevant HPC suite passes.
8. The two Kimi deployments and retained Gemma deployment pass live model-aware
   checks; source pins, checkpoint, and mode-600 secrets match the contract.

### Repair revision

Recorded: 2026-10-11 01:21 PT

Native AutoData is pinned to
`d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`. That revision propagates only
reviewed checker/schema codes, removes raw exception content from workspace
state, and persists an idempotent three-strike permanent-failure circuit.

Trial 5 uses Kimi without a filesystem mount namespace. Therefore raw provider,
broker, supervisor, bridge, and training diagnostics are discarded rather than
written anywhere below the Kimi-visible attempt root. Research-visible feedback
contains only validated codes, static summaries, retryability, and bounded
numeric metadata.

## Plan

Recorded: 2026-10-11 01:01 PT

1. Complete the feedback-propagation audit and all identified Run 12 repairs.
2. Commit native AutoData first and update the AAR pin to its exact SHA.
3. Commit the AAR repair and Trial 4/5 records without unrelated dirty work.
4. Synchronize both exact commits and run complete native plus AAR HPC tests.
5. Launch Trial 5 automatically after the final runtime preflight.
6. Monitor every lifecycle transition through verified training smoke or a
   fail-closed stop, maintaining `PROGRESS.md` and `TIMINGS.md`.

## Pass criteria

Recorded: 2026-10-11 01:01 PT

Trial 5 passes only if:

1. All pre-launch gates pass against the exact retained source revisions.
2. Authoring failures receive actionable safe codes and do not repeat because
   a specific checker cause was discarded.
3. Freeze produces exactly one canonical registered execution with `3/3/3`,
   disjoint `64/32/32`, and valid grounding/holdout digests.
4. Native meta-optimization completes exactly three iterations and finalizes a
   provenance-bound winner without using held-out tasks.
5. Production attempts 1,250 fresh source tasks at c32 and publishes exactly
   1,000 accepted rows with at least 0.95 successful-task fraction.
6. The handoff and consumption receipt bind the same 1,000 rows and hashes;
   one optimizer step completes and a non-empty loadable PEFT adapter passes.
7. The attempt stops after training smoke with no evaluator, held-out scoring,
   publication, or promotion.

## Stop criteria

Recorded: 2026-10-11 01:01 PT

Stop and preserve evidence if any pre-launch gate is missing; a failure is
generic when a reviewed safe cause exists; raw protected content crosses a
feedback boundary; a stable failure repeats beyond its bound; any exact
execution/partition/budget/provenance contract differs; registration or
submission cannot reconcile idempotently; production, handoff, optimizer,
adapter, or loadability verification fails; an evaluator starts; or the user
requests a stop.

## Monitoring

Record meaningful transitions in `PROGRESS.md` and durable intervals/counters
in `TIMINGS.md`. Monitoring is read-only and must not mutate the live attempt,
relax gates, expose generated content, or repair a running workspace in place.

## After a pass

Recorded: 2026-10-11 01:01 PT

Retain the adapter, dataset and consumption receipts, execution intents,
source/config pins, partition/holdout digests, feedback evidence, budget
accounting, and timing report. Do not evaluate or promote the adapter without a
separate explicit request.
