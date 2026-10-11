# Run 12 Canary 2 Trial 13

**Experiment code branch:** `autodata`

- Status: stopped at 16:01:54 PT; provider/judge health failure preserved
- Created: 2026-10-11 15:35 PT
- Last updated: 2026-10-11 16:03 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Run the unchanged confirmed Trial 12 scientific contract from a fresh attempt,
with corrected host-FSM re-entry after model-authored native action results.
Continuously monitor lifecycle completion and code health so stalls, repeated
retries, opaque failures, and unexpected job activity are caught before they
consume the remaining attempt budget.

## Context

Trial 12 failed before native execution because a corrected action result was
not consumed before generic stall detection. Trial 13 preserves Trial 12 and
runs from immutable AAR commit `6697babb3ea0158e1d41823491031bfbda172bc6`
with the re-entry repair. Its retained attempt root is
`/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T223822Z-6697babb3ea0`.

## Launch

The canary was launched through `submit_canary.sh`; do not launch this retained
attempt again. Slurm jobs are launch `1820603`, research `1820610`, and
controller `1820611`. The evaluator is disabled.

## Configuration

- Kimi-K2.6 researcher `aar_8-kimi26`.
- Kimi-K2.6 generator `autodata_8-kimi26`.
- Gemma 4 31B target deployment `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Luna judge `gpt-5-6-luna`, with at most two judge-format attempts.
- Exact `3/3/3`, disjoint `64/32/32`, concurrency 32.
- Production 1,250→1,000; five final feedback rounds; 707 native attempts.
- Campaign ceiling `$41,775`; stop after verified one-step training smoke.
- Evaluator disabled.

## Model and execution roles

- Researcher: Kimi-K2.6 through logical deployment `aar_8-kimi26`.
- Generator/teacher: Kimi-K2.6 through `autodata_8-kimi26`.
- Target probe and training base: Gemma 4 31B through fixed deployment
  `winnieyangwn-r12-alpha-i1-c0dab4f7`.
- Row judge: Luna `gpt-5-6-luna` through Model API.
- Proposal monitor, lifecycle supervisor, broker, comparator, and approvals:
  deterministic trusted code from the pinned AAR and AutoData snapshots.
- Evaluator inference model and evaluator judge: not used by this canary.

## Trial 12 repair

Trial 12 failed before native execution because a corrected action result was
not consumed before generic stall detection. Trial 13 immediately consumes a
ready result after each tool turn and treats trusted action, feedback, strategy,
and handoff artifacts as durable progress. Trial 12 remains preserved.

## Monitoring and code-health goal

Monitoring continues through terminal training-smoke success. Each observation
must check:

- Slurm state, job churn, dependency correctness, and unexpected evaluator or
  training jobs.
- Lifecycle-supervisor heartbeat, phase age, subject identity, and forward
  transitions.
- Repeated identical action/result or validation-feedback digests, repeated
  phases, and exhausted stall counters.
- Task, provider, schema, judge-format, target-feedback, and native-attempt
  retry growth, including repeated retries that make no durable progress.
- Tracebacks, crashes, OOMs, timeouts, malformed responses, contract failures,
  and loss of precise error feedback.
- Scientific/data-health signals that can make later completion impossible,
  especially acceptance rate, remaining native-attempt budget, partition
  integrity, and production yield.

Trial 13 was stopped before production at 16:01:54 PT. It was not hung: all
three meta-optimization iterations completed and the execution reached
`final_pending`. The retained receipts instead exposed a provider-health
failure: 172 Luna HTTP-429 outcomes and 85 tasks that each exhausted two
completed but contract-invalid judge responses. This monitor goal remains a
required gate for the repaired successor trial.

## Pass criteria

- Exact three-iteration meta-optimization completes with verified lineage.
- Production retains exactly 1,000 contract-valid rows from 1,250 initial
  tasks without weakening the judge or partitions.
- The verified training handoff produces a real-GPU one-optimizer-step smoke
  receipt.
- No evaluator launches and no unresolved code-health warning remains.

## Stop criteria

Stop and preserve evidence on any new code defect, identity drift, evaluator
start, contract failure, stale supervisor heartbeat, repeated no-progress retry
loop, exhausted attempt budget, or production yield that cannot meet the exact
row contract. Do not mutate or resume a failed retained attempt.
