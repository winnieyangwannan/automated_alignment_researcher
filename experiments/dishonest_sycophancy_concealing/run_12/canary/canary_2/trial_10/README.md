# Run 12 Canary 2 Trial 10

**Experiment code branch:** `autodata`

- Status: prelaunch validation
- Created: 2026-10-11 04:04 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Complete the confirmed Run 12 bootstrap canary after repairing the launch-path
alias defect exposed by Trial 9. Run exactly three meta-optimization iterations
over disjoint `64/32/32` partitions, produce and verify 1,000 accepted rows from
1,250 source tasks at concurrency 32, consume the verified handoff in one real
optimizer step, save a non-empty loadable PEFT adapter, and stop before
evaluation.

## Fixed contract

The user's standing same-configuration replacement-trial authorization applies.
Trial 10 changes only the run identity and committed integration repairs.

- Researcher: Kimi-K2.6 deployment `aar_8-kimi26`.
- Generator: Kimi-K2.6 deployment `autodata_8-kimi26`.
- Semantic/proposal monitor: Claude Opus 4.8.
- Target/training model: `gemma-4-31B-it` at the fixed shared checkpoint.
- Retained target deployment: `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: `gpt-5-6-luna`.
- Meta contract: exact `3/3/3`, disjoint `64/32/32`, concurrency 32.
- Production contract: 1,250 source tasks and 1,000 accepted rows.
- Campaign ceiling: `$5,500`.
- Stop boundary: verified `training_smoke`; evaluator disabled.

## Repairs carried into this trial

- `7b7d73e`: normalize and validate AAR/native action results, preserve
  correctable leases, propagate retry feedback, and retain privileged service
  diagnostics.
- `d38aa7c`: canonicalize launcher and shared runtime repository roots before
  containment and snapshot classification, preserving the strict immutable
  profile identity check across FAIR's `/home` and `/storage/home` aliases.

## Launch and monitoring

Launch only from the exact synchronized commit after local, HPC, native-engine,
configuration, source, checkpoint, secret, and live endpoint gates pass:

```bash
AAR_RUN12_REUSE_BASE_DEPLOYMENT=winnieyangwn-r12-alpha-i1-c0dab4f7 \
  canary/canary_2/trial_10/submit_canary.sh
```

Stop and preserve evidence on any new code defect, contract failure, identity
drift, evaluator start, or user stop request. Never repair retained live state.

## Pass criteria

1. Immutable AAR/native sources and runtime bindings pass fail-closed gates.
2. Trusted orchestration creates and registers exactly one canonical execution.
3. All three meta iterations complete under the exact partition/budget contract.
4. Production yields exactly 1,000 verified accepted rows from 1,250 tasks.
5. One optimizer step consumes the verified handoff and saves a valid adapter.
6. The trial stops at training smoke with no evaluator or held-out publication.
