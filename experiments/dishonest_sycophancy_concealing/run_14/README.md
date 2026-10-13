# Run 14: Opus 5 AutoData comparison

**Experiment code branch:** `autodata`

- Status: prepared; not launchable; not launched
- Created: 2026-10-12 23:46 PT
- Last updated: 2026-10-12 23:46 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Determine whether Claude Opus 5 performs better than Claude Opus 4.8 on the
same mutable-challenge AutoData data-generation loop used by Run 13 Canary
Trial 14.

The intentional treatment is limited to two model roles: the AAR researcher
and delegated monitor use Opus 5, and the AutoData semantic optimizer plus
per-task generator/challenger use Opus 5. All other configuration remains
identical to the Run 13 Trial 14 reference.

## Context

The comparison reference is
`experiments/dishonest_sycophancy_concealing/run_13/canary/trial_14` at setup
source commit `cf801547196f52a92a139434e52cc0377e02ceaa`.

Run 13 Trial 14 tests a typed mutable `challenge_strategy`, exactly ten meta
iterations, 1,250 fresh production tasks, 1,000 accepted rows, and a verified
one-step Gemma training smoke before stopping. Run 14 preserves those settings
and the same `dishonest_sycophancy_concealing_v2` recipe so model version is the
only scientific treatment.

The existing Run 13 launcher, scheduled payloads, recovery helper, lifecycle
coordinator fences, and shared team launcher are fail-closed to the Run 13
identity and Opus 4.8. They must be extended and reviewed before this Run 14
configuration can be launched. This setup deliberately does not bypass those
guards.

## Model and execution roles

- AAR researcher and delegated monitor: Claude Opus 5, model
  `claude-opus-5`, logical deployment `meta-claude-cli-opus-5`, through the
  Meta Claude CLI with maximum effort.
- AutoData semantic optimizer and per-task generator/challenger: Claude Opus
  5, provider model `claude-5-opus`, logical deployment
  `meta-model-api-claude-5-opus`, through Model API Responses at
  `https://api.meta.ai/v1/responses`.
- AutoData row judge: `gpt-5-6-luna` through Model API Responses, unchanged.
- Target probe and training base: Gemma 4 31B IT, fixed base before training,
  unchanged.
- Evaluator inference and evaluator judge: not used; evaluation is disabled at
  the `training_smoke` stop boundary.
- Trusted orchestration, lifecycle transitions, approvals, budgets, receipts,
  comparison logic, and protected paths: deterministic host code with AutoData
  revision `f53bc2136905461ffdbba0a203a12e351e184aaf`, unchanged.

The Model API catalog available during setup listed `claude-5-opus`; no model
inference call was made. These role assignments must be explicitly reconfirmed
before any launch, as required by the experiment-organization contract.

## Launch

Recorded: 2026-10-12 23:46 PT

Run 14 is intentionally not launchable yet. There is no operator command until
the Run 13-specific recovery and lifecycle fences have a reviewed Run 14 path,
the Opus 5 researcher identifier has passed the exact Claude CLI preflight, and
the resulting launcher is covered by focused contract tests.

The future entrypoint belongs at:

```text
experiments/dishonest_sycophancy_concealing/run_14/canary/opus5_autodata_comparison/launch/launch.sh
```

Creating this documentation and configuration is not launch authorization.

## Pass criteria

- The resolved Run 14 configuration differs from Run 13 Trial 14 only in run
  identity, runtime-profile reference, researcher model/deployment, and AutoData
  generator model/deployment.
- Native meta-optimization completes all ten configured iterations and records
  every candidate decision.
- Final test evidence satisfies AutoData quality, challenge, and validity
  constraints without hidden-evidence leakage.
- Production exports exactly 1,000 independently accepted rows from 1,250
  fresh tasks with authenticated provenance.
- AAR consumes the export and produces a verified one-optimizer-step Gemma
  training receipt and loadable PEFT adapter.
- No evaluator job launches.
- The retained comparison reports like-for-like Opus 5 versus Opus 4.8 outcome
  and process metrics; the canary score is not treated as a scientific result.

## Stop criteria

Stop before submission if model-role confirmation is absent; if the resolved
parity check has any unreviewed difference; if Opus 5 model identity or access
is unverified; or if any Run 13-only fence would be bypassed rather than
explicitly extended.

During execution, stop on any identity, immutable-artifact, budget, approval,
provenance, export, or training-contract violation; protected-file mutation;
preserved-component drift during pressure rewrites; hidden-evidence leakage;
or evaluator launch.

## Directory layout

```text
run_14/
├── README.md
├── PLAN.md
├── PROGRESS.md
└── canary/
    ├── README.md
    └── opus5_autodata_comparison/
        ├── config/run.yaml
        ├── README.md
        └── PROGRESS.md
```

The shared Opus 5 runtime profile is
`configs/autodata/target_aware_model_api_claude_opus_5_c8_v1.yaml`.

## Configuration and invariants

- One `alpha` chain and one structural target pair.
- Stop after verified `training_smoke`; evaluator disabled.
- Exactly ten meta iterations with 64 tuning, 32 validation, and 32 test
  tasks.
- AutoData concurrency `8`, provider attempts `5`, and finalization passes `3`.
- Mutable recipe file limited to `recipe/generation_strategy.json`.
- Production requests 1,250 fresh tasks and requires 1,000 accepted rows.
- Gemma 4 31B IT target/training base, GPT-5.6 Luna row judge, recipe, pinned
  AutoData source, budgets, storage policy, and all non-model fields remain
  unchanged from Run 13 Trial 14.

## Monitoring and recovery

No attempt or job exists. Append future state transitions to the canary's
`PROGRESS.md` in PT, retaining attempt paths, exact job IDs, model identities,
configuration hashes, and held-out-safe evidence paths.

The intended comparison records each candidate strategy diff; per-iteration
quality, challenge, validity, and utility; pressure-rewrite conversion and
diversity; preserved-component hashes; and final test evidence relative to the
Run 13 Trial 14 Opus 4.8 reference.

## Isolation and provenance

Runtime evidence belongs under the configured `/checkpoint/ram/{user}` root,
not in Git. Do not record credentials, raw hidden examples, evaluator-private
traces, or partial held-out scores in research-readable files. Any future
attempt must snapshot the exact source commit, resolved configuration and
hashes, AutoData revision, model identities, seeds, receipts, and proof paths.
