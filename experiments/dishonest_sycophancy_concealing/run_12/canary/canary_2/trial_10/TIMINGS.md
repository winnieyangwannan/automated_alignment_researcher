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
