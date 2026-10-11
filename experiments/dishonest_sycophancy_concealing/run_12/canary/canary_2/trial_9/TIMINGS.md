# Run 12 Canary 2 Trial 9 lifecycle timings

All displayed timestamps use Pacific Time (`PT`).

## Attempt identity

- Status at 2026-10-11 03:59 PT: prelaunch validation.
- Run ID: `run12-canary2-trial9`.
- AAR repair revision: `7b7d73e025684f85a661cf75d9b3bca58411d6f2`.
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
✓ Trial 8 evidence preserved
✓ Action-result/diagnostic repair committed
✓ Exact repair commit synchronized to HPC
✓ Local and HPC focused regression
⏳ Trial 9 record commit and immutable preflight
○ Launcher
○ Research allocation
○ Workspace authoring and freeze
○ Canonical meta baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```

## Terminal prelaunch timing

- Preflight began: approximately 04:00 PT.
- Live Kimi/MCP proof: passed.
- Immutable config compilation: failed at approximately 04:01 PT.
- Slurm jobs created for Trial 9: 0.
- Research, controller, training, production, and evaluator time: 0 seconds.
- Preserved attempt:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T110006Z-ce9163e152f2`.

```text
✓ Committed source selected
✓ Live Kimi/MCP proof
✗ Logical /home repository root disagreed with /storage/home realpath
✓ Compiler rejected mismatched immutable config locations
✓ No Trial 9 Slurm job or evaluator was created
```
