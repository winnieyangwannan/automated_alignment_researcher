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

## Terminal timing

- Workspace proposal/authoring/freeze: 03:39–03:47 PT.
- Canonical baseline: completed by 03:48:39 PT; 96/699 attempts used.
- Analysis action: completed at approximately 03:49:05 PT.
- Native transition retries: failed without state progress through 03:49:33 PT.
- Research `1814230`: 03:30:53–03:49:50 PT, `FAILED 1:0`.
- Controller `1814231`: terminal reconciliation through 03:50:18 PT,
  `FAILED 1:0`.
- Trial outcome: stopped before meta iteration 1 mutation.
- Production, handoff, training, and evaluator time: 0 seconds.
- Root cause confirmed by isolated native replay at 03:56 PT.

```text
✓ Canonical lineage routing
✓ Exact canonical baseline
✓ Analysis action lease/completion
✗ AAR envelope was not flattened to native action-result fields
✓ Failed closed before mutation/production/training/evaluation
✓ Retained Trial 8 evidence remained unchanged during diagnosis
```
