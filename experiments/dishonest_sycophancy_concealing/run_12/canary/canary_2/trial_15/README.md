# Run 12 Canary 2 Trial 15

**Experiment code branch:** `autodata`

- Status: staged; not launched
- Created: 2026-10-11 16:55 PT
- Last updated: 2026-10-11 16:55 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 16:55 PT

Repeat Trial 14's confirmed scientific and provider-health contract from a
fresh immutable attempt, using lower overall concurrency, bounded transient
Luna retries, and server-enforced structured judge output.

## Context

Recorded: 2026-10-11 16:55 PT

Trial 13 completed all three meta-optimization iterations without a hang, then
stopped before production after its retained receipts exposed 172 Luna HTTP-429
outcomes and 85 tasks that exhausted two contract-invalid judge responses.

Trial 14 then failed before meta-optimization because the trusted retry
validator rejected its configured three-attempt policy. Commit
`03aa0157e4601991b946c5975fc97b6ebc85c5a2` fixes that validator mismatch.
Trial 15 otherwise preserves Trial 14's exact roles, target reuse, partitions,
iteration contract, provider settings, production target, and budget.

## Model and execution roles

- Researcher: Kimi-K2.6 through logical deployment `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 through logical deployment
  `autodata_8-kimi26`.
- Target probe and training base: Gemma 4 31B through fixed logical deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Model API with three bounded transport
  attempts for HTTP 429 or transient 5xx responses.
- Proposal monitor, lifecycle supervisor, broker, comparator, and approvals:
  deterministic trusted code from pinned AAR and AutoData source snapshots.
- Evaluator inference model and evaluator judge: not used; evaluator disabled.

## Launch

Recorded: 2026-10-11 16:55 PT

Launch only from the clean matching HPC worktree after pinned source commit
`03aa0157e4601991b946c5975fc97b6ebc85c5a2` is synchronized and validated.
The operator entrypoint is:

```bash
bash experiments/dishonest_sycophancy_concealing/run_12/canary/canary_2/trial_15/submit_canary.sh
```

## Plan

Recorded: 2026-10-11 16:55 PT

1. Synchronize and validate the retry-validator repair.
2. Launch one fresh attempt and monitor provider health, lifecycle progress,
   retry growth, native-attempt consumption, and unexpected Slurm activity.
3. Stop at verified one-step training smoke; never launch an evaluator.

## Configuration and invariants

- Exact meta-optimization contract: minimum 3, maximum 3, patience 3.
- Exact disjoint task partitions: 64 tuning, 32 validation, 32 held-out test.
- Overall task concurrency: 8; the profile permits three bounded
  model-transport attempts.
- Production contract: 1,250 initial tasks and exactly 1,000 retained rows.
- Five target-feedback attempts; at most two judge-format attempts.
- Campaign ceiling: `$41,775`.
- Stop boundary: verified one-step `training_smoke`; evaluator disabled.

## Pass criteria

Recorded: 2026-10-11 16:55 PT

- Transient transport retries are bounded and honor `Retry-After`.
- Luna responses use the verified strict Responses JSON Schema and retain
  local semantic validation.
- Exact three-iteration meta-optimization completes with verified lineage and
  healthy provider/contract telemetry.
- Production retains exactly 1,000 contract-valid rows from 1,250 initial
  tasks without weakening the judge or task partitions.
- The verified training handoff produces a real-GPU one-optimizer-step smoke
  receipt; no evaluator launches and no unresolved code-health warning remains.

## Stop criteria

Recorded: 2026-10-11 16:55 PT

Once launched, stop and preserve evidence on repeated terminal 429s,
judge-contract exhaustion, a no-progress loop, identity drift, stale supervisor
heartbeat, unexpected evaluator start, task-partition violation, exhausted
native-attempt budget, or production yield that cannot satisfy the exact
1,000-row contract.

## After a pass

Recorded: 2026-10-11 16:55 PT

Retain the resolved configuration, proof, request/retry telemetry, source
revisions, job IDs, receipts, and training-smoke evidence under the durable
attempt root. A pass authorizes review of the retained canary only; it does not
authorize evaluator work or alteration of earlier trials.
