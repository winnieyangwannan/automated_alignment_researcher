# Run 12 Canary 2 Trial 12 lifecycle timings

All displayed timestamps use Pacific Time (`PT`).

## Attempt identity

- Status at 2026-10-11 06:24 PT: awaiting explicit model/config confirmation.
- Run ID: `run12-canary2-trial12`.
- Required AAR repair: `b8629a8fa3374111a1b55e40b1a9d114c7e5650d`.
- Required native repair: `da9e12a43710ced9d407822e55c6e7c541e57a27`.
- Required meta iterations: 3/3.
- Required partitions: 64 tuning, 32 validation, 32 held-out test.
- Required concurrency: 32.
- Native attempt ceiling: 707.
- Campaign ceiling: `$24,100`.
- Production tasks/rows: 1,250/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, required throughout.

## Lifecycle

```text
✓ Trial 11 evidence preserved
✓ Budget/broker repairs committed and synchronized
✓ Local and HPC regression gates
⏳ Explicit model/config confirmation
○ Trial 12 source commit and synchronization
○ Launcher
○ Research allocation
○ Workspace authoring and freeze
○ Canonical baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```
