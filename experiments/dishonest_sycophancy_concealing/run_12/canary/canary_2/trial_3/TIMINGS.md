# Run 12 Canary 2 Trial 3 lifecycle timings

Human-readable timing and bottleneck report. All displayed timestamps use
Pacific Time (`PT`). Evidence will be derived from durable Slurm accounting,
native AutoData state, lifecycle events, broker metadata, handoff receipts, and
training records. No generated rows, raw prompts, target responses,
credentials, or held-out information belong here.

## Attempt identity

- Status at 2026-10-10 23:01 PT: prepared; not launched.
- Source commit: pending Trial 3 setup commit.
- Attempt root: not created.
- Checkpoint root: not created.
- Pipeline, research, controller, training, and evaluator jobs: none.

## Measurement sources

- Planned: committed submission metadata and resolved configuration.
- Planned: Slurm `sacct`, `squeue`, and job logs.
- Planned: native workspace/execution state and lifecycle-supervisor status.
- Planned: broker task-result metadata, production manifest, handoff and
  consumption receipts, and adapter verification record.

## Current lifecycle

```text
○ Source/config validation
○ Endpoint and MCP preflight
○ Infrastructure bootstrap
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

## Work and quality counters

- Authoring checks: 0.
- Authoring dry-run tasks: 0.
- Native meta-optimization executions/candidates: 0.
- Production source tasks: 0/1,250.
- Production accepted rows: 0/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, as required.

## Unmeasured stages

Endpoint preflight, submission, queueing, research/method authoring, proposal
review, workspace authoring, baseline approval, native meta-optimization,
production, handoff verification, and training smoke have not started.
