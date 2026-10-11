# Run 12 Canary 2 lifecycle timings

Human-readable timing and bottleneck report for the production-data-to-training
canary. All displayed timestamps use Pacific Time (`PT`). This report is updated
from durable run evidence; it does not contain credentials, generated training
rows, evaluator traces, or held-out scores.

Operational events and recovery decisions are recorded separately in
[PROGRESS.md](PROGRESS.md).

## Attempt identity

- Status at 2026-10-10 17:19 PT: running in the second baseline-review cycle.
- Source commit: `5f1861ebebc897d22e9fcfb7dee4073ebb2f19d4`.
- Wrapper job: `1808967`.
- Research-chain job: `1808973`.
- Controller job: `1808974`.
- Attempt root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261010T235309Z-5f1861ebebc8`.
- Team root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261010T235309Z-5f1861ebebc8/aar_teams/run12-gemma4-31b-kimi26-alpha-1808967`.

## Measurement sources

The lifecycle does not yet emit one monolithic timing file. This report combines
the following durable sources:

- Slurm accounting for queue, wrapper, research-chain, controller, and future
  training-job durations.
- `metadata/kimi_mcp_preflight.json` for endpoint/MCP preflight completion.
- `timings/chain_gemma4_31b_explore_alpha.jsonl` for instrumented research
  phases and approval-model calls.
- `autodata/native/state.db` for native action, execution, candidate, and task
  timestamps.
- `autodata/native/lifecycle-supervisor-status.json` and the supervisor log for
  stage transitions and heartbeat evidence.
- Content-addressed `autodata.baseline-review/v1` artifacts and broker results
  for dry-run task durations, outcomes, metrics, and model-call counts.

Source timestamps stored in UTC are converted to PT for this report. Durations
come from recorded timestamps or Slurm accounting rather than conversational
estimates.

## Current lifecycle

```text
✓ Attempt setup and endpoint/MCP preflight
✓ Wrapper and research-chain admission
✓ Research and method authoring
✓ Proposal review
✓ AutoData workspace bootstrap
✓ Design clarification
✓ Grounding authoring and approval
✓ Pipeline revision 1 and baseline 1
✓ Pipeline revision 2 and baseline 2
⏳ Baseline approval 2
○ Meta-optimization
○ Production generation
○ Training smoke
```

## Completed intervals

### Attempt setup and scheduling

- Attempt setup and Kimi preflight: 16:53:09–16:53:42.954 PT, approximately
  34 seconds.
- Wrapper queue: 16:53:46–16:55:49 PT, 2 minutes 3 seconds.
- Wrapper execution: 16:55:49–16:56:11 PT, 22 seconds.
- Research-chain queue: 16:55:59–16:58:30 PT, 2 minutes 31 seconds.

### Research and proposal

- Research and method authoring: 16:58:42–17:02:31.477 PT, approximately
  3 minutes 49 seconds.
- Proposal review: 17:02:31.477–17:02:37.142 PT, 5.665 seconds.
- Proposal-bound workspace bootstrap completed at approximately 17:02:37 PT.

### AutoData workspace authoring

- `clarify_design`: 17:02:38–17:03:08 PT, 30 seconds.
- `author_grounding`: 17:03:08–17:09:12 PT, 6 minutes 4 seconds.
- `approve_grounding`: 17:09:12–17:09:56 PT, 44 seconds end-to-end.
  The timed approval-model call was 5.021 seconds; the remainder was agent/tool
  orchestration.
- Pipeline revision 1 authoring: 17:09:59–17:10:57 PT, 58 seconds.
- Baseline 1: approximately 17:10:59–17:14:04 PT, 3 minutes 5 seconds.
  - Recipe check: near-instant.
  - Dry-run task 1: 98 seconds.
  - Dry-run task 2: 86 seconds.
  - Sequential dry-run throughput: approximately 0.65 tasks/minute.
- Baseline approval 1: 17:14:04–17:14:35 PT, 31 seconds end-to-end.
  The timed approval-model call was 7.246 seconds and requested a revision.
- Pipeline revision 2 authoring: 17:14:37–17:16:08 PT, 1 minute 31 seconds.
- Baseline 2: approximately 17:16:13–17:18:32 PT, 2 minutes 19 seconds.
  - Recipe check: 2 seconds.
  - Dry-run task 1: 70 seconds.
  - Dry-run task 2: 64 seconds.
  - Sequential dry-run throughput: approximately 0.90 tasks/minute.
- Baseline approval 2: pending from 17:18:32 PT at this snapshot.

## Work and quality counters

- Grounding: 128 scenarios split into 64 tuning, 32 validation, and 32 test
  tasks.
- Workspace-authoring task executions: 6/6 operationally successful: two recipe
  checks and four dry-run tasks.
- Meta-optimization executions and candidates: 0; this stage has not started.
- Production accepted rows: 0; production has not started.
- Training jobs: 0; training has not started.
- HTTP 429, provider-call, broker, gateway, and infrastructure failures: 0.

Baseline 2 improved target challenge, but both samples still failed the complete
acceptance contract:

- Sample 1: quality `0.66`, challenge `0.5`, valid `0`.
- Sample 2: quality `0.96`, challenge `1.0`, valid `0`.
- Each sample completed five Kimi generator calls, four Gemma target calls, and
  five Luna judge calls: 14 model calls per task.

The retained baseline artifact records call counts but not individual provider
call durations, so the 70- and 64-second task walls cannot be safely apportioned
between Kimi, Gemma, and Luna.

## Preliminary bottleneck observations

- Grounding authoring is the longest completed single authoring action at
  6 minutes 4 seconds.
- The second pipeline revision reduced mean dry-run wall time from 92 seconds to
  67 seconds, approximately 27% faster. Sequential throughput rose from about
  0.65 to 0.90 tasks/minute.
- No infrastructure or rate-limit bottleneck is visible yet.
- The current concern is acceptance quality: the revised baseline became more
  challenging but remained invalid. Additional authoring revisions may add more
  wall time before meta-optimization begins.
- These two sequential baseline samples do not predict concurrency-32 production
  throughput. Meta-optimization and production must be measured separately.

## Pending final measurements

The report will be extended when each stage starts or finishes with:

- Total workspace-authoring duration and revision count.
- Per-meta-iteration wall time, task counts, acceptance, quality, challenge,
  throughput, retries, and failure classes.
- Production wall time, tasks attempted/succeeded, accepted rows, rows/minute,
  model-call counts, retries, and rate-limit evidence.
- Handoff verification and one-step training queue/runtime.
- Total canary wall time, critical path, and concrete recommendations for the
  five-chain run.
