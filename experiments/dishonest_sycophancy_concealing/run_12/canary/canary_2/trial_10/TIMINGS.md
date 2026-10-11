# Run 12 Canary 2 Trial 10 lifecycle timings

All displayed timestamps use Pacific Time (`PT`).

## Attempt identity

- Status at 2026-10-11 04:04 PT: prelaunch validation.
- Run ID: `run12-canary2-trial10`.
- AAR path repair revision: `d38aa7ca7083fcbac9892a22c7ac808f49b8f5e4`.
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
✓ Trial 9 evidence preserved
✓ Canonical-path repair committed and synchronized
✓ HPC /home→/storage/home identity proof
⏳ Trial 10 record commit and immutable preflight
○ Launcher
○ Research allocation
○ Workspace authoring and freeze
○ Canonical meta baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```

## Live attempt

- Attempt root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T110535Z-9d6a25606a38`.
- Immutable AAR source: `9d6a25606a38c95653af02c3e74281bd3293aa3c`.
- Launcher `1814684`: completed at 04:08:52 PT, `COMPLETED 0:0`.
- Research `1814688`: created at 04:08 PT.
- Controller `1814689`: created at 04:08 PT, dependency-gated.
- Evaluator job: absent.

## Terminal outcome

- Research allocation: 04:10:20–04:33:37 PT, 23m17s, `FAILED 1:0`.
- Controller terminal handling: 04:33:39–04:33:55 PT, 16s, `FAILED 1:0`.
- Canonical meta execution: baseline plus iterations 1–3 completed; reached
  `final_pending`, iteration 3/3, 547/699 attempts.
- Final full-corpus work: 26 successes and 6 typed row failures recorded before
  supervisor cleanup terminated the active finalization step.
- Root cause: unchanged supervisor status exceeded the 180-second host-FSM
  heartbeat SLA during a legitimate long-running native step.
- Containment: zero evaluator jobs, production executions, handoffs, training
  jobs, training receipts, verified smoke markers, checkpoints, submissions, or
  score artifacts.
- Recovery decision at 04:37 PT: preserve Trial 10; commit the 30-second active
  step heartbeat repair and launch a fresh Trial 11.
