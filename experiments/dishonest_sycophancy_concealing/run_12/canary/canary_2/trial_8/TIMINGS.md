# Run 12 Canary 2 Trial 8 lifecycle timings

All displayed timestamps use Pacific Time (`PT`).

## Attempt identity

- Status at 2026-10-11 03:28 PT: child chain launched; research queued.
- Run ID: `run12-canary2-trial8`.
- AAR repair revision: `207f05ebc86f0d789d84e094af2b247d1987aa59`.
- Native AutoData revision required:
  `d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`.
- Required meta iterations: 3/3.
- Required partitions: 64 tuning, 32 validation, 32 held-out test.
- Required concurrency: 32.
- Production tasks/rows: 1,250/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, required throughout.
- Attempt root:
  `/checkpoint/ram/winnieyangwn/aar-runs/run12-bootstrap-canary/20261011T102402Z-68d01f27c0ba`.
- Immutable AAR source: `68d01f27c0baf5cdd03c636006219add5c009f1a`.
- Launcher `1814192`: 03:28:02–03:28:42 PT, `COMPLETED 0:0`.
- Research `1814230`: submitted 03:28:33 PT.
- Controller `1814231`: submitted 03:28:33 PT, dependency-gated.

## Lifecycle

```text
✓ Trial 7 evidence preserved
✓ Lineage/recovery repair committed
✓ Exact commit synchronized to HPC
✓ Local and HPC focused regression
✓ Trial 8 record commit and immutable preflight
✓ Launcher
⏳ Research allocation
○ Workspace authoring and freeze
○ Canonical meta baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```
