# Run 12 progress

Last updated: 2026-10-09 08:52 PDT

## Current state

Run 12 implementation and source validation are complete. The dedicated merged
Gemma endpoint has been submitted and is waiting for its coordinator allocation.
Endpoint preflight and the one-task AutoData canary have not been submitted yet.

## Completed

- Selected a real successful Run 7 candidate with headline score `32.84` as the
  simulated previous-iteration incumbent.
- Confirmed its adapter declares the fixed base
  `/checkpoint/ram/shared/models/google/gemma-4-31B-it`.
- Confirmed the existing atomic merged checkpoint has 13 shards and
  `62,546,336,448` merged-weight bytes.
- Added `aar.autodata.target-binding/v1` creation and fail-closed validation.
- Extended the existing model-broker canary with an optional target-aware mode.
- Added tests for binding round-trip, tamper rejection, three-provider
  provenance, and rejected-row handling.
- Added one-task endpoint and broker launch scripts under `run_12/`.
- Documented the persistent per-chain logical endpoint design and immutable
  iteration-versioned backends.
- Devserver focused unit tests: 8 passed.
- HPC focused pytest: 8 passed.
- HPC Ruff checks: passed.
- Synchronized the exact source history to the clean HPC `autodata` branch.
  Current synchronized commit: `cd1e04845a6007f075349b2d6c668610452a3222`.
- Rendered and inspected the validated Gemma deployment configuration:
  vLLM 0.25.1, language-model-only mode, one GB300 GPU, tensor parallel 1,
  gateway registration enabled, gateway default disabled.
- Submitted dedicated deployment `winnieyangwn-run12-gemma4-cshc`.

## Live infrastructure

- Coordinator Slurm job: `1782982`
- Coordinator state at last check: `PENDING`
- Pending reason at last check: `None` reported by Slurm
- Endpoint workers ready: 0 of 1
- Proxy ready: no
- Gateway route ready: no
- Configured lifetime: one day
- Configured checkpoint: the selected Run 7 merged candidate

The endpoint is dedicated to Run 12. It does not replace a gateway default and
does not modify the protected evaluator deployment.

## Next actions

1. Wait for coordinator job `1782982` to run.
2. Verify the coordinator selects the exact configured merged checkpoint.
3. Wait for one healthy vLLM worker and proxy.
4. Verify direct model listing, deterministic generation, and gateway routing
   by deployment ID.
5. Submit `submit_run_12.sh preflight` and wait for `preflight.json`.
6. Submit `submit_run_12.sh canary <attempt-root>` and wait for
   `canary-report.json`.
7. Verify three provider calls and exact target provenance.
8. Record timing and any failure/acceptance result.
9. Stop the temporary deployment after the retained evidence is complete.

## Timing so far

- Source implementation and focused validation: complete.
- Endpoint deployment submitted: 2026-10-09 08:51 PDT.
- Endpoint startup duration: in progress.
- Endpoint preflight duration: not started.
- One-task AutoData duration: not started.

## Known non-blocking distinction

The one generated row may be rejected by Luna or may fail the Gemma-challenge
gate. That would mean the sampled scenario is not suitable training data, not
that adapter attachment failed. Infrastructure success is determined by the
completed three-provider task and exact deployment/checkpoint provenance.
