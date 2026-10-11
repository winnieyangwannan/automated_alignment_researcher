# Run 16 one-chain native-generation lifecycle check

- Status: planned; not launched
- Created: 2026-10-11 01:49 PT
- Last updated: 2026-10-11 01:49 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 01:49 PT

Prove one complete Claude Opus 4.8 research → native data generation → proposal approval →
real-GPU one-step training → two-item evaluation → finding lifecycle without
loading or producing any AutoData component or artifact.

## Context

Recorded: 2026-10-11 01:49 PT

This is the first ordered Run 16 gate before the five-chain topology check and
the full run. It exercises the hardened failure/recovery code on fresh state.
Its bounded score is workflow evidence, not a scientific result.

## Launch

Recorded: 2026-10-11 01:49 PT

After the documented model-role mapping is explicitly confirmed and the final
clean commit is synchronized, launch with:

```bash
experiments/dishonest_sycophancy_concealing/run_16/canary/one_chain_lifecycle_check/launch/launch.sh
```

## Plan

Recorded: 2026-10-11 01:49 PT

Launch one `canary` seed with one research session, a one-step PEFT training
job, and one one-GPU evaluator for exactly two `verbalized_ece` items. The
evaluator starts on demand only after the smoke proof passes and the pipeline
stages that exact adapter into the submission queue.

## Model and execution roles

Recorded: 2026-10-11 01:49 PT

This canary uses native model-authored data generation. AutoData is disabled,
so there is no AutoData generator, target probe, row judge, broker, workspace,
or comparator role.

```text
AAR control plane
├─ AAR researcher and native data-generation author
│  └─ Claude Opus 4.8, model claude-opus-4-8 at maximum effort
│     Meta Claude CLI with secure internet and research process isolation
├─ AAR proposal-approval monitor
│  └─ claude-4-8-opus through Meta Model API
│     Reviews method policy, reproducibility, leakage, and data provenance
├─ AAR training model
│  └─ Gemma 4 31B IT fixed base + a new PEFT adapter
│     Runs locally in the one-step GPU training job; it is not an API
└─ AAR evaluator
   └─ Gemma 4 31B IT base + the canary's candidate adapter through vLLM
      Runs on one GPU for exactly two verbalized_ece items
```

`verbalized_ece` is rule-scored, so this canary makes no evaluator-judge model
call. The broader multidimensional configuration retains `gpt-5-6-luna` through
Meta Model API for model-judged benchmarks, but that role is not exercised by
this gate. Deployment names are stable logical identities; runtime preflight
discovers and health-checks the physical proxy address.

## Pass criteria

Recorded: 2026-10-11 01:49 PT

- The resolved configuration records `data_generation.backend=native` and
  `AAR_AUTODATA=0`.
- The generated method has declared data provenance and passes proposal review.
- A non-empty loadable adapter, one score, and one matching result finding exist
  for the same run ID.
- No AutoData plugin, broker, workspace, state database, recipe execution, or
  production export exists in the attempt.

## Stop criteria

Recorded: 2026-10-11 01:49 PT

Stop on any AutoData initialization, missing provenance, method-contract
failure, invalid adapter, evaluator failure, or score/finding mismatch.

## After a pass

Recorded: 2026-10-11 01:49 PT

Create and review the fail-closed lifecycle proof, then supply that exact proof
to the five-chain topology gate. A one-chain pass does not directly authorize
the full run. Do not treat the bounded score as a scientific conclusion.
