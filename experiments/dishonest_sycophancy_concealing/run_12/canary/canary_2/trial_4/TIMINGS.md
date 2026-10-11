# Run 12 Canary 2 Trial 4 lifecycle timings

Human-readable timing and bottleneck report. All displayed timestamps use
Pacific Time (`PT`). Evidence will be derived from durable Slurm accounting,
native AutoData state, lifecycle events, broker metadata, execution-intent and
registration records, handoff receipts, and training records. No generated
rows, raw prompts, target responses, credentials, or held-out information
belong here.

## Attempt identity

- Status at 2026-10-11 00:54:05 PT: stopped during pipeline authoring.
- Source commit: `9b993a73310a7280508921c7ef662dc2af277500`.
- Attempt root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T073731Z-9b993a73310a`.
- Checkpoint root:
  `/checkpoint/ram/winnieyangwn/aar-checkpoints/run12-bootstrap-canary/20261011T073731Z-9b993a73310a`.
- Launch/pipeline job: `1811750`, completed successfully in 21 seconds.
- Research job: `1811790`, ran 12 minutes 15 seconds, then cancelled by user
  authorization.
- Controller job: `1811791`, cancelled while dependency-held and never started.
- Training job: never submitted.
- Evaluator jobs: none, as required.

## Pre-launch timing gates

- Trusted canonical manifest construction must follow workspace freeze without
  a researcher action.
- Native creation plus control registration must complete within 60 seconds or
  three attempts, whichever is reached first.
- Budget reservation must be computed for the exact canonical meta and
  production workload before submission.

## Measurement sources

- Planned: committed submission metadata and resolved configuration.
- Planned: durable execution-intent, native lineage, registration attempts, and
  task/holdout digest records.
- Planned: Slurm `sacct`, `squeue`, and job logs.
- Planned: native workspace/execution state and lifecycle-supervisor status.
- Planned: broker task-result metadata, phase budget accounting, production
  manifest, handoff and consumption receipts, and adapter verification record.

## Current lifecycle

```text
● Guardrail implementation and regression validation (275 passed; 5 subtests)
● Budget reservation proof and operator decision
● Fresh model-role and configuration confirmation
● Source commit and HPC synchronization
● Endpoint and MCP preflight
● Infrastructure bootstrap
◐ Method authoring and contract check (contract passed; pipeline failed)
● Proposal review and approval
○ Canonical execution create/register
○ Baseline approval
○ Three-iteration meta-optimization
○ Production
○ Training smoke
```

## Completed intervals

- 23:53 PT: Trial 4 launch-blocked documentation and configuration setup began.
- 00:07 PT: the user approved the `$5,500` campaign ceiling.
- 00:11 PT: the user confirmed the exact model-role and launch mapping.
- 00:35 PT: the reusable lifecycle repair passed local static and focused
  recovery validation; complete HPC validation remained pending.
- 00:38 PT: complete HPC validation and live endpoint preflight passed; job
  `1811750` submitted Trial 4 exactly once.
- 00:40 PT: pipeline `1811750` completed after 21 seconds and emitted research
  `1811790` plus controller `1811791`; no evaluator was submitted.
- 00:41:50 PT: research `1811790` began after the scheduler queue wait.
- 00:45 PT: the method contract passed, the proposal was submitted, and trusted
  bootstrap registered workspace `ws_00ce21e80399454f9b021cb4e58905f5`;
  `clarify_design` became the current scoped action.
- 00:53 PT: pipeline authoring remained pending after seven identical protected
  checker failures were reduced to generic `solve_failed`; no freeze, baseline,
  or execution had begun.
- 00:54:05 PT: the user authorized a stop; research `1811790` and controller
  `1811791` were cancelled. Final state was `pipeline_pending` revision 21 with
  eight identical checker failures and zero executions.

## Work and quality counters

- Native execution intents: 0.
- Native executions: 0.
- Registration attempts: 0.
- Authoring checks and dry-run tasks: 0.
- Required meta-optimization iterations: 0/3.
- Production source tasks: 0/1,250.
- Production accepted rows: 0/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, as required.

## Unmeasured stages

Baseline review, execution, production, training, and evaluation were never
entered and therefore have no runtime measurements.
