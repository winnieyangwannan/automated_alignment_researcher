# Run 12 Canary 2 Trial 7

**Experiment code branch:** `autodata`

- Status: running; research job `1813738`, controller `1813739`, no evaluator
- Created: 2026-10-11 02:30 PT
- Last updated: 2026-10-11 03:05 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 02:30 PT

Prove the complete bounded AutoData-to-training lifecycle after repairing the
native-freeze/AAR-adapter contract mismatch exposed by Trial 6. Complete exactly
three meta-optimization iterations over disjoint `64/32/32` partitions,
produce and verify 1,000 accepted rows from 1,250 source tasks at concurrency
32, consume the complete handoff in one real optimizer step, save a valid
non-empty PEFT adapter, and stop before evaluation.

## Context

Recorded: 2026-10-11 02:30 PT

Trial 6 passed immutable launch, authoring, pipeline checks and dry runs,
baseline approval, and workspace freeze. It then failed before canonical
execution creation because the trusted AAR adapter rejected four fields that
native AutoData always serializes at freeze. Trial 7 uses the same confirmed
experiment contract and a fresh run ID after the adapter accepts those known
fields, ignores their values, and reconstructs all authoritative execution
settings from trusted operator configuration.

## Model and execution roles

Carried forward unchanged under the user's standing same-configuration
replacement-trial authorization confirmed at 2026-10-11 02:29 PT.

| Role                                | Model or implementation           | Backend / identity                                |
| ----------------------------------- | --------------------------------- | ------------------------------------------------- |
| Researcher and visible host agent   | Kimi-K2.6                         | Kimi CLI; deployment `aar_8-kimi26`               |
| Data generator and teacher          | Kimi-K2.6                         | Local broker; deployment `autodata_8-kimi26`      |
| Proposal and semantic monitor       | Claude Opus 4.8                   | FAIR Model API; fail-closed                       |
| Baseline operational approval       | Deterministic trusted AAR policy  | Local signed approval bridge                      |
| Target probe and training base      | `gemma-4-31B-it`                  | Fixed checkpoint; vLLM 0.25.1 language-model-only |
| Retained target deployment          | `gemma-4-31B-it`                  | `winnieyangwn-r12-alpha-i1-c0dab4f7`              |
| Row-quality and challenge judge     | `gpt-5-6-luna`                    | FAIR Model API                                    |
| AutoData orchestration/comparator   | Trusted deterministic native code | Pinned, feedback-safe AutoData revision           |
| Evaluator inference/evaluator judge | Not used                          | Trial stops after verified training smoke         |

The fixed target/training checkpoint is
`/checkpoint/ram/shared/models/google/gemma-4-31B-it`. Concurrency is `32`, the
campaign ceiling is `$5,500`, and the stop boundary is `training_smoke`. Any
change to these confirmed fields requires fresh user confirmation.

## Launch

Recorded: 2026-10-11 02:30 PT

Launch only after the focused repair is committed, synchronized exactly to
`fair-cw-use2-1`, passes the complete HPC regression gate, and passes source,
secret, checkpoint, configuration, and live endpoint preflight:

```bash
AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7 \
  canary/canary_2/trial_7/submit_canary.sh
```

The wrapper submits one `alpha` bootstrap canary and must retain the
`training_smoke`/no-evaluator contract.

## Plan

Recorded: 2026-10-11 02:30 PT

1. Commit the freeze-shape adapter repair and production-shaped regression.
2. Synchronize the exact commit to the matching clean HPC checkout.
3. Run the complete exact-commit HPC suite and live preflight.
4. Launch one immutable-source Trial 7 attempt.
5. Monitor every lifecycle transition and the mandatory absence of evaluator
   work; stop and repair before a replacement trial if another defect appears.

## Pass criteria

Recorded: 2026-10-11 02:30 PT

1. Immutable AAR/native snapshots and runtime bindings pass fail-closed gates.
2. The workspace freezes and trusted orchestration creates/registers exactly
   one canonical execution before the 60-second/three-attempt SLA expires.
3. The canonical manifest is exact `3/3/3`, disjoint `64/32/32`, concurrency
   32, with all source, contract, and holdout digests verified.
4. All three meta iterations complete, then production yields exactly 1,000
   accepted rows from 1,250 source tasks at the required coverage.
5. One real optimizer step consumes the verified handoff and produces a
   non-empty, loadable PEFT adapter.
6. The trial stops after verified training smoke with no evaluator or held-out
   scoring/publication.

## Stop criteria

Recorded: 2026-10-11 02:30 PT

Stop and preserve evidence if source/runtime identity drifts; any execution,
partition, budget, digest, provenance, registration, production, handoff,
training, adapter, or loadability contract fails; an evaluator starts; or the
user requests a stop. Never repair live retained experiment state in place.

## Monitoring

Record meaningful transitions in `PROGRESS.md` and intervals/counters in
`TIMINGS.md`. Monitoring is read-only and must not expose generated content,
credentials, or held-out data.

## After a pass

Recorded: 2026-10-11 02:30 PT

Retain the adapter, dataset and consumption receipts, execution intents,
source/config pins, partition/holdout digests, feedback evidence, budget
accounting, and timing report. Do not evaluate or promote the adapter without a
separate explicit request.
