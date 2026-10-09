# Run 13 progress

Last updated: 2026-10-09 03:37 PDT

## Current state

Run 13's dedicated merged-Gemma endpoint is serving and its endpoint preflight
passed. The target-aware AutoData canary has not been submitted yet; two fixes
learned from Run 12 are validated locally and awaiting commit/synchronization
before canary submission. Training, evaluation, and the full chain have not
been launched.

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
- Fast-forwarded the initial Run 13 implementation to the HPC `autodata`
  worktree.
- Launched dedicated deployment `winnieyangwn-run13-gemma4-cshc` from the
  clean pinned Gemma model-card checkout.
- Verified vLLM 0.25.1, language-model-only mode, the exact merged checkpoint,
  one healthy worker, authenticated direct model listing, smoke generation,
  gateway registration by deployment ID, and no gateway-default claim.
- Endpoint preflight job `1784170` passed against checkpoint binding
  `sha256:f4ca9e6a4ce4ad301b717a37a26373dff9938974dcb5653d53ca39f12a69b9d6`.
- Ported Run 12's validated Kimi deployment ID and AutoData `PYTHONPATH` fixes
  into Run 13; 10 focused tests pass with those changes.

## Live infrastructure

- Run 13 coordinator job: `1784007`, running
- Run 13 endpoint worker job: `1784022`, 1 of 1 ready
- Run 13 proxy job: `1784107`, ready
- Run 13 gateway route ready: yes, deployment-specific only
- Run 13 endpoint preflight: passed, job `1784170`
- Run 13 one-task AutoData canary: not submitted

No Run 12 job or deployment is claimed as Run 13 infrastructure.

## Next actions

1. Commit and synchronize the validated Run 13 canary fixes.
2. Re-run focused validation in the HPC environment.
3. Submit `submit_run_13.sh canary <attempt-root>` and wait for
   `canary-report.json`.
4. Verify three provider calls and exact target provenance.
5. Record timing and any failure/acceptance result.
6. Stop the temporary deployment after the retained evidence is complete.

## Timing so far

- Run 13 documentation initialized: 2026-10-09 03:15 PDT.
- Source implementation and focused validation: complete on the devserver.
- Endpoint deployment submitted: 2026-10-09 03:22 PDT.
- Endpoint serving: 2026-10-09 03:36 PDT.
- Endpoint preflight duration: 0.255 seconds.
- One-task AutoData duration: not started.

## Known non-blocking distinction

The one generated row may be rejected by Luna or may fail the Gemma-challenge
gate. That would mean the sampled scenario is not suitable training data, not
that adapter attachment failed. Infrastructure success is determined by the
completed three-provider task and exact deployment/checkpoint provenance.
