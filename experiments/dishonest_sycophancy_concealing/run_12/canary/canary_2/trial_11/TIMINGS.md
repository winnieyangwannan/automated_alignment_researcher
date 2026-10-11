# Run 12 Canary 2 Trial 11 lifecycle timings

All displayed timestamps use Pacific Time (`PT`).

## Attempt identity

- Status at 2026-10-11 04:38 PT: prelaunch validation.
- Run ID: `run12-canary2-trial11`.
- Supervisor-heartbeat repair revision:
  `9f81cdad899c51abc4cf589884f3ee0827c29ecd`.
- Native AutoData revision required:
  `d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`.
- Required meta iterations: 3/3.
- Required partitions: 64 tuning, 32 validation, 32 held-out test.
- Required concurrency: 32.
- Production tasks/rows: 1,250/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, required throughout.

## Lifecycle

```text
✓ Trial 10 evidence preserved
✓ Heartbeat repair committed and synchronized
✓ Local and HPC focused regression gates
⏳ Trial 11 record commit and immutable preflight
○ Launcher
○ Research allocation
○ Workspace authoring and freeze
○ Canonical meta baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```

## Prelaunch hardening

- 04:42 PT: independent review found uncovered heartbeat risk in synchronous
  reconciliation/transition work and configurable idle/retry waits.
- Trial 11 submission remained held; jobs and attempt roots created: 0.
- Generalized heartbeat and serialized shutdown validation: 119 tests plus 6
  subtests passed locally.
- Broader AutoData/Run 12 validation: 326 tests plus 6 subtests passed; one
  unrelated test failed because user-owned dirty state deletes its Run 13
  fixture tree.

## Live attempt

- Attempt root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T114652Z-4511d687af23`.
- Immutable AAR source: `4511d687af23d7b52aa473b17bf3237451175e7f`.
- Immutable native source: `d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`.
- Launcher `1814907`: 04:49:25–04:50:01 PT, 36s, `COMPLETED 0:0`.
- Research `1814992`: submitted 04:49:48 PT; pending allocation at 04:50 PT.
- Controller `1814993`: submitted 04:49:48 PT; dependency-gated.
- Evaluator job: absent.
