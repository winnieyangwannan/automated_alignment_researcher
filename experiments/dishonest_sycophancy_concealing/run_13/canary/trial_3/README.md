# Run 13 Canary Trial 3: config-driven runtime profile validation

**Experiment code branch:** `autodata`

- Status: authorized; awaiting source validation and launch
- Created: 2026-10-11 23:32 PT
- Last updated: 2026-10-11 23:32 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Run one `alpha` chain through native AutoData production and one verified Gemma
optimizer step, then stop at `training_smoke` without evaluation.

## Context

Trial 1 exposed protocol-blind Kimi proxy setup. Trial 2 corrected transport
routing but failed before method authoring because runtime validation still used
a hard-coded legacy profile-name registry. Trial 3 validates the selected strict
checked-in profile config, including its name and security invariants.

## Launch

From the isolated HPC checkout, launch only through this thin wrapper:

```bash
AAR_RUN13_CANARY_ROOT=<reviewed-run13-proof-root> \
AAR_RUN13_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN13_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_13/canary/trial_3/submit_canary.sh
```

The wrapper selects this exact config and delegates to the shared root launcher
and Slurm engine. Direct root-launcher use is rejected.

## Plan

Complete research and proposal approval, author and freeze the native AutoData
workspace, run bounded meta-optimization and production, verify exactly 1,000
accepted rows, consume that export in one real-GPU Gemma PEFT optimizer step,
and stop.

## Model and execution roles

- AAR researcher: Claude Opus 4.8 through `meta-claude-cli-opus-4-8`, maximum effort.
- Proposal monitor: Claude Opus 4.8 through Meta Model API.
- AutoData generator: `claude-4-8-opus` through
  `meta-model-api-claude-4-8-opus`, `model_api_responses`.
- Target probe and training base: fixed Gemma 4 31B IT checkpoint.
- AutoData row judge: `gpt-5-6-luna` through Meta Model API.
- Evaluator inference and evaluation judge: not used.
- Broker, approvals, lifecycle state, comparator, and receipts: trusted code.

## Pass criteria

The retained completion proof must join the approved proposal, native workspace,
meta-optimization, verified 1,000-row production export, and one-step loadable
adapter receipt under `trial3`, while proving no evaluator or promotion started.

## Stop criteria

Stop on source/config/model drift, profile name/config disagreement, a Kimi
proxy requirement on the Responses route, missing lifecycle approval or receipt,
incomplete production, failed GPU training smoke, or any evaluator launch.

## After a pass

Retain the trial-scoped attempt, source/config hashes, provider accounting,
handoff receipt, adapter manifest, and training-smoke proof. Do not scale or
evaluate without separate authorization.
