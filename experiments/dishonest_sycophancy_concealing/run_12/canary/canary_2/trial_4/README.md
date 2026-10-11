# Run 12 Canary 2 Trial 4

**Experiment code branch:** `autodata`

- Status: repaired and locally validated; launch-blocked pending commit,
  synchronization, and the complete HPC test/preflight gate
- Created: 2026-10-10 23:53 PT
- Last updated: 2026-10-11 00:35 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-10 23:53 PT

Prove the complete bounded AutoData-to-training lifecycle after repairing the
execution-control failure exposed by Trial 3. Trial 4 must establish a trusted
operational baseline, atomically create and register the canonical native
execution, complete exactly three meta-optimization iterations over disjoint
`64/32/32` partitions, produce and verify exactly 1,000 accepted rows from
1,250 source tasks at concurrency 32, consume those rows in one real optimizer
step, save a valid non-empty PEFT adapter, and stop before evaluation.

## Context

Recorded: 2026-10-10 23:53 PT

Trial 3 proved the repaired provider-provenance path through authoring and
operational baseline approval, but then failed its protocol. Workspace freeze
created an unregistered default execution, and the later supervised path
accepted another default manifest with `minimum_iterations=0`,
`maximum_iterations=1`, null patience, and empty explicit partitions. Native
AutoData consequently used a fallback split that included the intended held-out
tasks. That wrong execution consumed the `$299` campaign reservation before any
required `3/3` execution or production run began.

Trial 4 is a fresh attempt specification. It must not reuse or mutate any Trial
3 workspace, execution, result, or campaign. It is intentionally not launchable
until the trusted-orchestration repair and its regression tests are committed,
validated, and synchronized.

## Model and execution roles

Recorded: 2026-10-10 23:53 PT

| Role                                | Model or implementation             | Backend / identity                                      |
| ----------------------------------- | ----------------------------------- | ------------------------------------------------------- |
| Researcher and visible host agent   | Kimi-K2.6                           | Kimi CLI; deployment `aar_8-kimi26`                     |
| Data generator and teacher          | Kimi-K2.6                           | Local broker; deployment `autodata_8-kimi26`            |
| Proposal and semantic monitor       | Claude Opus 4.8                     | FAIR Model API; fail-closed                             |
| Baseline operational approval       | Deterministic trusted AAR policy    | Local signed approval bridge                            |
| Target probe and training base      | `gemma-4-31B-it`                    | vLLM 0.25.1, language-model-only, fixed base checkpoint |
| Planned Trial 4 target deployment   | `gemma-4-31B-it`                    | `winnieyangwn-r12-alpha-i1-c0dab4f7`                    |
| Row-quality and challenge judge     | `gpt-5-6-luna`                      | FAIR Model API                                          |
| AutoData orchestration/comparator   | Deterministic trusted AAR/AutoData  | Pinned source; protected comparator                     |
| Evaluator inference/evaluator judge | Not used                            | Trial stops after training smoke                        |

The target and training base checkpoint is
`/checkpoint/ram/shared/models/google/gemma-4-31B-it`. This mapping is copied
from the user-confirmed Trial 3 mapping. At 00:11 PT on 2026-10-11, the user
explicitly confirmed this exact Trial 4 mapping together with concurrency `32`,
the `$5,500` campaign ceiling, and the stop-after-training-smoke boundary. Any
role, backend, deployment, checkpoint, concurrency, cap, or stop-boundary
change requires fresh confirmation before submission.

## Launch

Recorded: 2026-10-10 23:53 PT

**Do not launch yet.** Trial 4 is blocked until all pre-launch gates below pass,
the exact repaired source is committed and synchronized to the matching clean
HPC worktree, the budget decision is resolved, and the user explicitly
reconfirms the complete model-role mapping for that configuration revision.

Only after those conditions are recorded may an operator run this committed
entrypoint from the Run 12 directory on `fair-cw-use2-1`:

```bash
AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7 \
  canary/canary_2/trial_4/submit_canary.sh
```

The wrapper delegates to the shared Run 12 submitter. It selects one `alpha`
bootstrap-canary chain, requests one target pair only for controller-schema
compatibility, stops after `training_smoke`, and must not launch an evaluator.
This documented command is not launch authorization.

### Mandatory pre-launch guardrail gates

All five safeguards must be implemented and covered by focused regression
tests before submission:

1. Trusted orchestration—not Kimi—constructs the canonical execution manifest
   immediately after workspace freeze. It must set
   `minimum_iterations=3`, `maximum_iterations=3`,
   `early_stop_patience=3`, and exact `64/32/32` partitions from the trusted
   resolved operator contract.
2. Native execution creation and lifecycle registration are one durable,
   idempotent intent transition. Recovery after a crash between them must
   resolve and register the same content-bound execution without creating a
   duplicate.
3. Registration has a 60-second or three-attempt SLA, whichever is reached
   first. Exhaustion fails loudly and preserves evidence instead of leaving a
   supervisor idle.
4. Before any native execution call, trusted validation rejects wrong iteration
   counts, wrong production settings, empty or overlapping partitions,
   non-unique IDs, missing held-out tasks, or a missing/invalid task and holdout
   digest binding.
5. The freeze-created default is cancelled only if it is unambiguously linked
   to this workspace, is still in its initial phase, and has zero task attempts.
   A progressed or ambiguous default is preserved and the attempt fails closed.

The canonical specification and its digest must come from the immutable
launch-time resolved contract, not researcher-authored fields or mutable child
environment overrides.

### Budget gate

Trial 3 exhausted its `$299` reservation before completing even the wrong
one-iteration execution. Trusted reservation math for the corrected contract
requires capacity for `608` meta task evaluations plus two `1,250`-task
production attempts. At the configured conservative reservation of
`$1.720896` per model-backed task, the bound is `$5,348.544768`, before a small
authoring margin.

At 00:07 PT on 2026-10-11, the user explicitly approved raising the Trial 4
campaign cap. The YAML now sets `max_cost_usd: "5500"`. This is a hard safety
ceiling, not a spending target. Trusted preflight must recompute the bound from
the resolved policy and reject any drift or insufficient cap before native
creation.

## Plan

Recorded: 2026-10-10 23:53 PT

1. Complete the five trusted-orchestration safeguards and regression coverage.
2. Validate the strict Trial 4 YAML, v1 recipe, source pins, retained target,
   role mapping, partition/digest contract, and budget reservation bound.
3. Commit and synchronize the exact source revision, then obtain fresh explicit
   model-role and configuration confirmation.
4. Launch one fresh attempt through this committed wrapper.
5. Monitor authoring and require the canonical execution intent to be created,
   registered, and advanced without researcher control or duplicate execution.
6. Observe exactly three meta iterations and a provenance-bound winner.
7. Observe 1,250 production source tasks, exactly 1,000 accepted rows, complete
   handoff consumption, one optimizer step, and a verified adapter; then stop.

## Pass criteria

Recorded: 2026-10-10 23:53 PT

Trial 4 passes only when all conditions hold:

1. Source, compiled configuration, v1 recipe, rubric, protected paths, target,
   source pins, budget, and freshly confirmed model roles match the retained
   attempt metadata.
2. The five mandatory pre-launch guardrails pass focused positive, rejection,
   crash-recovery, idempotency, SLA, and default-cancellation tests before the
   native execution path is invoked.
3. Authoring checks and dry runs succeed with complete generator, target, and
   judge provenance.
4. Freeze is followed by exactly one canonical, content-bound, registered
   execution with `3/3/3`, unique disjoint `64/32/32` task partitions, and the
   expected task/holdout digests. Kimi cannot select or alter these values.
5. Native meta-optimization completes exactly three iterations without touching
   held-out tasks or protected state, and the protected comparator finalizes a
   provenance-bound winner.
6. Production attempts 1,250 source tasks at concurrency 32, maintains at least
   0.95 successful-task fraction, and publishes exactly 1,000 accepted rows
   without weakening quality, challenge, provenance, or budget gates.
7. The handoff and consumption receipt bind the same 1,000 rows, hashes,
   rubric, target, and contract. The SFT loader consumes the full dataset, one
   optimizer step runs, and a non-empty loadable PEFT adapter is verified.
8. Timing and provider-health evidence are retained, and the attempt stops
   after training smoke with no evaluator, held-out scoring, publication, or
   promotion.

## Stop criteria

Recorded: 2026-10-10 23:53 PT

Stop and preserve evidence if any of the following occurs:

- Any pre-launch guardrail, budget proof, source/config validation, HPC
  synchronization, or fresh model-role confirmation is missing.
- The execution manifest differs from exact `3/3/3`, `64/32/32`, task/digest,
  production, or budget settings, or is constructed from researcher-controlled
  input.
- Creation/registration creates a duplicate, cannot recover its durable intent,
  or exceeds 60 seconds or three attempts.
- A freeze-created default is progressed, ambiguous, has any task attempt, or
  cannot be safely and uniquely linked before cancellation.
- Any partition is empty, duplicated, overlapping, missing from the 128-task
  universe, or inconsistent with the trusted held-out digest.
- Provider provenance, protected-state, quality, production, handoff,
  consumption, optimizer-step, adapter, or loadability verification fails.
- The campaign cannot reserve the validated required budget, any evaluator or
  held-out evaluation starts, or the user requests a stop.

## Monitoring

Recorded: 2026-10-10 23:53 PT

Record each meaningful transition in [`PROGRESS.md`](PROGRESS.md) and durable
intervals/counters in [`TIMINGS.md`](TIMINGS.md). Monitoring is read-only: it
must not approve rows, rewrite the recipe, relax gates, expose generated rows
or target responses, or mutate a live attempt. Every transition must include
the actual lifecycle state, job IDs, execution identity, and whether any later
stage began.

## After a pass

Recorded: 2026-10-10 23:53 PT

Preserve the verified adapter, dataset receipt, execution-intent and
registration records, source/configuration identities, partition and holdout
digests, provider evidence, budget accounting, and timing report. Do not start
evaluation or promote the adapter without a separate explicit request.
