# Run 13 progress

Last updated: 2026-10-09 03:20 PDT

## Current state

Run 13 documentation and its endpoint-preflight/target-canary submitter are
implemented with Claude Opus 4.8 selected as the AAR researcher. No Run 13
endpoint deployment, preflight, AutoData canary, training, evaluation, or full
chain has been launched yet.

## Completed

- Preserved Run 12's adapter-target attachment, routing, provenance, isolation,
  promotion, and persistent per-chain endpoint design.
- Selected `AAR_AGENT_BACKEND=claude` and
  `AAR_AGENT_MODEL=claude-opus-4-8` for the final scored run.
- Kept Kimi-K2.6 as the AutoData generator and Luna as the AutoData judge.
- Kept the same successful Run 7 candidate, fixed Gemma base, merged-checkpoint
  strategy, and trusted target-binding protocol for the canary specification.
- Assigned Run 13-specific deployment and artifact names:
  `winnieyangwn-run13-gemma4-cshc` and
  `/storage/home/$USER/aar-runs/run13-adapter-target/`.
- Created `README.md`, `plan.md`, and `progress.md` for Run 13.
- Added Run 13-specific preflight, target-canary, and submission scripts with
  separate Slurm names, artifact paths, campaign ID, deployment ID, and
  environment-variable namespace.
- Shell syntax validation: passed.
- Focused target-binding, broker-canary, and Run 13 launch tests: 10 passed.

## Live infrastructure

- Run 13 coordinator job: not submitted
- Run 13 endpoint workers ready: 0
- Run 13 proxy ready: no
- Run 13 gateway route ready: no
- Run 13 endpoint preflight: not submitted
- Run 13 one-task AutoData canary: not submitted

No Run 12 job or deployment is claimed as Run 13 infrastructure.

## Next actions

1. Commit the Run 13 files and focused supporting changes.
2. Fast-forward the exact commit to the clean HPC `autodata` worktree.
3. Re-run validation in the HPC environment.
4. Launch and verify deployment `winnieyangwn-run13-gemma4-cshc` against the
   exact configured merged checkpoint.
5. Submit `submit_run_13.sh preflight` and wait for `preflight.json`.
6. Submit `submit_run_13.sh canary <attempt-root>` and wait for
   `canary-report.json`.
7. Verify three provider calls and exact target provenance.
8. Record timing and any failure/acceptance result.
9. Stop the temporary deployment after the retained evidence is complete.

## Timing so far

- Run 13 documentation initialized: 2026-10-09 03:15 PDT.
- Source implementation and focused validation: complete on the devserver.
- Endpoint deployment: not submitted.
- Endpoint startup duration: not started.
- Endpoint preflight duration: not started.
- One-task AutoData duration: not started.

## Known non-blocking distinction

The one generated row may be rejected by Luna or may fail the Gemma-challenge
gate. That would mean the sampled scenario is not suitable training data, not
that adapter attachment failed. Infrastructure success is determined by the
completed three-provider task and exact deployment/checkpoint provenance.
