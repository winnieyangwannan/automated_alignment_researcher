# Run 12 Canary 2 Trial 3

**Experiment code branch:** `autodata`

- Status: stopped; protocol failure preserved
- Created: 2026-10-10 23:01 PT
- Last updated: 2026-10-10 23:57 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-10 23:01 PT

Prove the complete bounded AutoData-to-training lifecycle after repairing the
two provenance defects exposed by Trial 2. Trial 3 must establish a trusted
operational baseline, complete exactly three native meta-optimization
iterations, produce and verify exactly 1,000 accepted rows from 1,250 source
tasks, consume those rows in one real optimizer step, save a valid non-empty
PEFT adapter, and stop before evaluation.

## Context

Recorded: 2026-10-10 23:01 PT

Trial 2 reached the native baseline gate twice but never entered
meta-optimization. Its first completed attempt proved that raw task results
contained generator, target, and judge provenance, but pinned AutoData dropped
that list while serializing `TaskResult`. AutoData commit
`8ed79b55843d259deea9132cf257f02ff7eb5ee9` preserves the list.

The next attempt proved that serialization fix, then exposed a recipe defect:
the Kimi generator deployment ID was used for request routing but omitted from
the durable usage record. AAR commit
`8b83f841862c2381c714996b6467075805f342c3` records the deployment ID and adds
task-level fail-fast validation for provider roles, request IDs, generator
deployment, target checkpoint, and judge identity. Trial 3 is a fresh attempt;
it must not reuse or mutate any Trial 2 workspace or result artifact.

## Model and execution roles

Recorded: 2026-10-10 23:01 PT

| Role                                | Model or implementation              | Backend / identity                                      |
| ----------------------------------- | ------------------------------------ | ------------------------------------------------------- |
| Researcher and visible host agent   | Kimi-K2.6                            | Kimi CLI; deployment `aar_8-kimi26`                     |
| Data generator and teacher          | Kimi-K2.6                            | Local broker; deployment `autodata_8-kimi26`            |
| Proposal and semantic monitor       | Claude Opus 4.8                      | FAIR Model API; fail-closed                             |
| Baseline operational approval       | Deterministic trusted AAR policy     | Local signed approval bridge                            |
| Target probe and training base      | `gemma-4-31B-it`                     | vLLM 0.25.1, language-model-only, fixed base checkpoint |
| Trial 3 target deployment           | `gemma-4-31B-it`                     | `winnieyangwn-r12-alpha-i1-c0dab4f7`                    |
| Row-quality and challenge judge     | `gpt-5-6-luna`                       | FAIR Model API                                          |
| AutoData orchestration/comparator   | Deterministic AutoData and AAR code | Pinned AutoData `8ed79b5`; protected comparator         |
| Evaluator inference/evaluator judge | Not used                             | Trial stops after training smoke                        |

The target and training base checkpoint is
`/checkpoint/ram/shared/models/google/gemma-4-31B-it`. Any change to a model,
deployment, checkpoint, backend, or role assignment requires fresh explicit
user confirmation before submission.

## Launch

Recorded: 2026-10-10 23:01 PT

After model-role confirmation, commit and synchronize the exact `autodata`
source revision to the matching clean HPC worktree, then run from the Run 12
directory on `fair-cw-use2-1`:

```bash
AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7 \
  canary/canary_2/trial_3/submit_canary.sh
```

The wrapper delegates to the shared committed Run 12 submitter. It launches one
`alpha` bootstrap-canary chain, requests one target pair for controller-schema
compatibility, stops after `training_smoke`, and must not launch an evaluator.

## Plan

Recorded: 2026-10-10 23:01 PT

1. Validate the strict Trial 3 YAML, reviewed v1 recipe, source pins, model-role
   mapping, retained fixed-base endpoint, and focused provenance tests.
2. Launch a fresh unique attempt through the committed submitter.
3. Monitor proposal/workspace authoring and prove that baseline samples retain
   complete generator, target, and judge provenance.
4. Require baseline approval to create the first native meta execution.
5. Observe exactly three meta-iterations and a provenance-bound winner.
6. Observe production of exactly 1,000 accepted rows from 1,250 source tasks at
   concurrency 32 and at least 0.95 successful-task fraction.
7. Verify handoff identity, full contracted-loader consumption, one optimizer
   step, and a non-empty loadable adapter; then stop.

## Pass criteria

Recorded: 2026-10-10 23:01 PT

Trial 3 passes only when all conditions hold:

1. Source, compiled configuration, staged v1 recipe, rubric digest, protected
   paths, target deployment, checkpoint, and model-role mapping match the
   confirmed Trial 3 specification.
2. Authoring checks and dry runs succeed with complete generator, target, and
   judge provenance. Generator usage must identify `autodata_8-kimi26`; target
   usage must identify the confirmed deployment and checkpoint hash.
3. Baseline approval remains operational: trustworthy `valid=0` diagnostics
   may inform authoring but remain non-exportable.
4. The workspace advances into native meta-optimization and completes exactly
   three configured iterations without changing a protected file.
5. The protected comparator finalizes a provenance-bound winning pipeline.
6. Production attempts 1,250 source tasks at concurrency 32, maintains at
   least 0.95 successful-task fraction, and publishes exactly 1,000 accepted
   rows without weakening teacher-quality or target-challenge gates.
7. The handoff and consumption receipt bind the same 1,000 rows, hashes,
   rubric, target, and contract. The SFT loader consumes the full dataset, one
   real optimizer step runs, and a non-empty loadable PEFT adapter is verified.
8. Timing and provider-health evidence are retained, and the run stops after
   training smoke with no evaluator, held-out scoring, publication, or
   promotion.

## Stop criteria

Recorded: 2026-10-10 23:01 PT

Stop and preserve evidence if any of the following occurs:

- Source, recipe, rubric, protected paths, target checkpoint, deployment, or
  confirmed model-role identity drifts.
- Any successful task result or baseline sample lacks required provider roles,
  unique request IDs, generator deployment, target deployment/checkpoint, or
  judge identity.
- Baseline approval rejects solely because a trustworthy diagnostic row has
  low content metrics, repeatedly revises without creating a native execution,
  or reaches a configured budget or no-progress limit.
- A rejected row becomes exportable or bypasses schema, teacher-quality,
  target-challenge, or provenance checks.
- Meta-optimization does not complete all three iterations, changes protected
  state, cannot compare candidates, or cannot finalize a winner.
- Production cannot meet its fixed task, success-fraction, or accepted-row
  contract after the authorized retry, or encounters an unresolved provider,
  broker, gateway, target, or storage failure.
- Handoff, loader consumption, optimizer-step count, adapter identity, or
  loadability verification fails.
- Any evaluator or held-out evaluation starts, or the user requests a stop.

## Monitoring

Recorded: 2026-10-10 23:01 PT

Record every meaningful transition in [`PROGRESS.md`](PROGRESS.md) and durable
intervals/counters in [`TIMINGS.md`](TIMINGS.md). Monitoring is read-only: it
must not approve rows, change the recipe, relax gates, expose generated rows or
target responses, or mutate a live attempt. Every transition must include the
actual lifecycle state, job IDs, and whether later stages began.

## After a pass

Recorded: 2026-10-10 23:01 PT

Preserve the verified adapter, dataset receipt, source/configuration identities,
provider evidence, and timing report. Do not start evaluation or promote the
adapter from this canary without a separate explicit request.
