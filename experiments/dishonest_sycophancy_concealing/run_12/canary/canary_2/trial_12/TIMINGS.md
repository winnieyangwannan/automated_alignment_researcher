# Run 12 Canary 2 Trial 12 lifecycle timings

All displayed timestamps use Pacific Time (`PT`).

## Attempt identity

- Status at 2026-10-11 14:40 PT: final model/config confirmation received;
  immutable launch synchronization is in progress.
- Run ID: `run12-canary2-trial12`.
- Required AAR repair: `b8629a8fa3374111a1b55e40b1a9d114c7e5650d`.
- Required native repair: `28a9c22125dc0cf101ebabc1b22408b4e974678a`.
- Required meta iterations: 3/3.
- Required partitions: 64 tuning, 32 validation, 32 held-out test.
- Required concurrency: 32.
- Native attempt ceiling: 707.
- Judge format attempts: at most 2 total per semantic round.
- Campaign ceiling: `$41,775` (derived worst case `$41,774.49216`).
- Production tasks/rows: 1,250/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, required throughout.

## Lifecycle

```text
✓ Trial 11 evidence preserved
✓ Budget/broker repairs committed and synchronized
✓ Local and HPC regression gates
✓ Explicit model/config confirmation
⏳ Trial 12 source commit and synchronization
○ Launcher
○ Research allocation
○ Workspace authoring and freeze
○ Canonical baseline and three iterations
○ Production and verified handoff
○ One-step training smoke
```
