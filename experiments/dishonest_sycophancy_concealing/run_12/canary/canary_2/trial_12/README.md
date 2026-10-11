# Run 12 Canary 2 Trial 12

**Experiment code branch:** `autodata`

- Status: awaiting explicit model/config confirmation
- Created: 2026-10-11 06:24 PT
- Last updated: 2026-10-11 06:24 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Complete the Run 12 bootstrap canary under the corrected native and campaign
budget contracts: three meta iterations over disjoint `64/32/32` partitions,
1,000 verified rows from 1,250 production tasks, one real optimizer step, and a
stop before evaluation.

## Context

Trial 11 completed baseline and all three iterations, then exhausted an
under-sized 699-attempt native ceiling during finalization. The systematic
audit also found incomplete provider-round accounting and a nonterminal broker
cost-overage path. AAR repair `b8629a8` and native repair `da9e12a` correct both
layers. Trial 11 remains preserved and is not resumed.

## Model and execution roles

- Researcher: Kimi-K2.6 deployment `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 deployment `autodata_8-kimi26`.
- Semantic/proposal monitor: Claude Opus 4.8.
- Target/training model: fixed `gemma-4-31B-it` shared checkpoint.
- Retained target deployment: `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: `gpt-5-6-luna`.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.
- Trusted orchestration, broker, comparator, approval, and budget gates:
  deterministic code.

## Fixed contract

- Meta: exact `3/3/3`, disjoint `64/32/32`, concurrency 32.
- Native capacity: 608 evaluations + 3 checks + 96 retry attempts = 707.
- Production: 1,250 source tasks, 1,000 accepted rows.
- Final-generation feedback: at most five visible rounds per task.
- Model HTTP transport attempts: exactly one per request.
- Campaign ceiling: `$24,100`; worst-case derived requirement
  `$24,099.427584` across 14,004 provider-round reservations.
- Stop boundary: verified `training_smoke`; evaluator disabled.

## Launch

After explicit confirmation of the model mapping and this configuration
revision, launch only from the exact synchronized commit:

```bash
AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7 \
  canary/canary_2/trial_12/submit_canary.sh
```

## Plan

Run one alpha bootstrap chain through immutable preflight, authoring, canonical
meta optimization, production, verified handoff, and one-step training smoke.
The independent monitor tracks lifecycle state and absence of evaluator work.

## Pass criteria

1. Immutable AAR `b8629a8` descendant and native `da9e12a` sources pass gates.
2. Trusted orchestration registers exactly one 707-attempt canonical execution.
3. Baseline and all three required iterations complete.
4. Production yields exactly 1,000 verified accepted rows from 1,250 tasks.
5. One optimizer step saves a non-empty loadable adapter.
6. The trial stops at training smoke with no evaluator or held-out publication.

## Stop criteria

Stop and preserve evidence on any new code defect, contract failure, identity
drift, evaluator start, or user stop request. Fix shared code and start a fresh
numbered trial; never mutate a failed retained attempt.

## After a pass

Retain the immutable attempt, verified handoff, training receipt, smoke proof,
and adapter provenance. Do not start evaluation without separate authorization.
