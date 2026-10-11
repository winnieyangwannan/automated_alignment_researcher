# Run 12 Canary 2 Trial 6 lifecycle timings

All displayed timestamps use Pacific Time (`PT`). No generated rows, raw
prompts, target responses, credentials, or held-out content belong here.

## Attempt identity

- Status at 2026-10-11 01:59 PT: prepared and launch-blocked.
- Run ID: `run12-canary2-trial6`.
- Native AutoData revision required:
  `d6e5619bab0b34a5913a4f8a2d3895047a3ff3bc`.
- AAR repair revision: pending focused commit.
- Trial 6 attempt root: not created.
- Trial 6 jobs: none.
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

## Work and quality counters

- Native execution intents and executions: 0.
- Authoring task attempts: 0.
- Required meta-optimization iterations: 0/3.
- Production source tasks: 0/1,250.
- Production accepted rows: 0/1,000.
- Training optimizer steps: 0/1.
- Evaluator jobs: 0, as required.

## Unmeasured stages

All Trial 6 runtime stages remain unmeasured because no Trial 6 attempt or job
has been created.
