# Run 12 Canary 2 Trial 3 lifecycle timings

Human-readable timing and bottleneck report. All displayed timestamps use
Pacific Time (`PT`). Evidence will be derived from durable Slurm accounting,
native AutoData state, lifecycle events, broker metadata, handoff receipts, and
training records. No generated rows, raw prompts, target responses,
credentials, or held-out information belong here.

## Attempt identity

- Status at 2026-10-10 23:57 PT: stopped; protocol failure and artifacts
  preserved.
- Source commit: `d6ff24e28e38af125ed7576133b44835acef262e`.
- Attempt root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T060442Z-d6ff24e28e38`.
- Checkpoint root:
  `/checkpoint/ram/winnieyangwn/aar-checkpoints/run12-bootstrap-canary/20261011T060442Z-d6ff24e28e38`.
- Pipeline job: `1810934`.
- Research job `1810943`: `FAILED` at 23:52:06 PT.
- Controller job `1810944`: `CANCELLED` at 23:56:17 PT.
- Automatic research retry `1811182`: `CANCELLED` at 23:56:17 PT.
- Training job: not yet submitted.
- Evaluator jobs: none, as required.

## Measurement sources

- Planned: committed submission metadata and resolved configuration.
- Planned: Slurm `sacct`, `squeue`, and job logs.
- Planned: native workspace/execution state and lifecycle-supervisor status.
- Planned: broker task-result metadata, production manifest, handoff and
  consumption receipts, and adapter verification record.

## Current lifecycle

```text
● Source/config validation
● Endpoint and MCP preflight
● Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ AutoData workspace registration
○ Baseline approval
○ Meta-optimization
○ Production
○ Training smoke
```

## Completed intervals

- 23:01 PT: Trial 3 documentation and configuration setup began.
- 23:02 PT: exact model and execution-role mapping explicitly confirmed.
- 23:05 PT: preflight completed and pipeline job `1810934` submitted.
- 23:06 PT: pipeline emitted research job `1810943` and controller job
  `1810944`; no evaluator job was emitted.
- 23:08 PT: pipeline job `1810934` was complete, research job `1810943`
  entered `RUNNING`, and controller job `1810944` remained dependency-held.
- 23:12:41 PT: exactly one fresh AutoData workspace was registered.
- 23:14:14 PT: authoring supervisor reported idle after continued stepping;
  no error or later-stage marker was present.
- 23:15:58–23:16:21 PT: operational baseline review completed with an
  `approve` decision.
- 23:16:23 PT: approved workspace froze and a fresh native execution began.
- 23:20:03 PT: native execution remained at `baseline_pending`, iteration `0`.
- 23:25 PT: native execution still had zero task attempts; the research job
  remained live with recent log activity and no error signal.
- 23:31:42 PT: durable control state showed no execution subject; Kimi had
  made no MCP call since baseline approval at 23:16:21 PT. Practical
  researcher-turn timeout checkpoint: approximately 23:54:44 PT.
- 23:39:55 PT: Kimi registered a new supervised preliminary execution.
- By 23:41:02 PT: all 128 preliminary baseline/selection attempts completed.
- 23:42:02–23:42:39 PT: mutation action created; execution remained active at
  `awaiting_mutation`.
- 23:42:58 PT: the sole permitted mutation completed.
- By 23:48 PT: execution had used 256 attempts; final corpus stopped after 41
  attempts because campaign reservation reached the `$299` cap.
- 23:52:06 PT: first research job failed; controller submitted one automatic
  retry.
- 23:56:17 PT: controller and automatic retry cancelled on user-authorized
  Trial 3 stop.
- 23:57 PT: all four Trial 3 job IDs were absent from `squeue`; evidence was
  preserved and the retained target deployment remained serving.

## Work and quality counters

- Authoring checks: 1/1 passed.
- Authoring dry-run tasks: 3/3 passed.
- Unintended one-iteration execution: 1 at `final_pending`; 256 total task
  attempts.
- Wrong execution final corpus: 41 attempts; 21 succeeded, 20 failed.
- Required three-iteration meta-optimization execution/candidates: 0.
- Production source tasks: 0/1,250.
- Production accepted rows: 0/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, as required.

## Unmeasured stages

Queueing, research/method authoring, proposal review, workspace authoring,
baseline approval, native meta-optimization, production, handoff verification,
and training smoke have not completed.
