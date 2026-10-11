# Run 12 Canary 2 Trial 4 lifecycle timings

Human-readable timing and bottleneck report. All displayed timestamps use
Pacific Time (`PT`). Evidence will be derived from durable Slurm accounting,
native AutoData state, lifecycle events, broker metadata, execution-intent and
registration records, handoff receipts, and training records. No generated
rows, raw prompts, target responses, credentials, or held-out information
belong here.

## Attempt identity

- Status at 2026-10-11 00:35 PT: repaired and locally validated; launch-blocked
  on commit, synchronization, and the complete HPC gate.
- Source commit: pending repaired Trial 4 commit.
- Attempt root: not created.
- Checkpoint root: not created.
- Pipeline, research, controller, training, and evaluator jobs: none.

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
◐ Guardrail implementation and regression validation (local pass; HPC pending)
● Budget reservation proof and operator decision
● Fresh model-role and configuration confirmation
○ Source commit and HPC synchronization
○ Endpoint and MCP preflight
○ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
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

All runtime stages are unmeasured because Trial 4 has not launched.
