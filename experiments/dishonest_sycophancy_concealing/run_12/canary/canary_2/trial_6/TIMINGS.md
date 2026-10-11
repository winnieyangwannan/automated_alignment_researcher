# Run 12 Canary 2 Trial 6 lifecycle timings

All displayed timestamps use Pacific Time (`PT`). No generated rows, raw
prompts, target responses, credentials, or held-out content belong here.

## Attempt identity

- Status at 2026-10-11 02:10 PT: launcher passed; research `1813007` queued;
  controller `1813008` dependency-held; evaluator absent.
- Run ID: `run12-canary2-trial6`.
- Native AutoData revision required:
  `d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`.
- AAR repair revision: `fb886848d58463cc4b7d5346cf9df2098c3181cb`.
- Trial 6 attempt root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T090839Z-fb886848d584`.
- Trial 6 launcher: `1812990`, initially `PENDING`.
- Research child: `1813007`.
- Controller: `1813008`.
- Evaluator jobs: 0, as required.

## Current lifecycle

```text
✓ Both Trial 5 pre-child failures preserved
✓ Immutable attempt-local source isolation proved
✗ Shared-interpreter handoff repair not yet validated
○ Focused repair commit and exact HPC synchronization
○ Complete HPC regression gate
○ Endpoint, source, and secret preflight
○ Infrastructure bootstrap
○ Method authoring and contract check
○ Proposal review and approval
○ Canonical execution create/register
○ Baseline approval
○ Three-iteration meta-optimization
○ Production
○ Training smoke
```

## Completed intervals inherited as pre-launch evidence

- 01:39:57–01:40:11 PT: Trial 5 launcher `1812591` ran for 14 seconds and
  failed closed with exit `2:0` after the shared worktree advanced during its
  queue wait. No child was submitted.
- 01:55:10 PT: Trial 5 immutable-source launcher `1812713` was submitted after
  its attempt-local AAR and native snapshots, source manifest, input copies,
  endpoint checks, and runtime preflight passed.
- 01:56:45–01:57:00 PT: launcher `1812713` ran for 15 seconds and failed with
  exit `127:0` when environment sourcing overwrote the valid shared
  `HARNESS_PY` with the nonexistent snapshot-local `.venv/bin/python`. No child
  was submitted.
- 01:59 PT: the same-configuration Trial 6 package was prepared under fresh run
  ID `run12-canary2-trial6`; it remained launch-blocked pending repair gates.
- 02:07:45–02:08:17 PT: exact HPC runtime gate job `1812944` completed `0:0`
  with 290 tests plus 9 subtests passing.
- 02:08 PT: exact source, native revision, secret, checkpoint, configuration,
  and three-endpoint live gates passed.
- 02:09 PT: fresh Kimi Bash-plus-MCP proof passed; Trial 6 launcher `1812990`
  was submitted and initially queued.
- 02:10:00–02:10:21 PT: launcher `1812990` completed `0:0`; child manifest
  recorded research `1813007`, controller `1813008`, and no evaluator.

## Work and quality counters

- Native execution intents and executions: 0.
- Authoring task attempts: 0.
- Required meta-optimization iterations: 0/3.
- Production source tasks: 0/1,250.
- Production accepted rows: 0/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, as required.

## Unmeasured stages

Research is queued for Slurm capacity. Downstream AutoData and training stages
remain unmeasured.
