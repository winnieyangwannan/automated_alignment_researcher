# Run 16 one-chain native-generation lifecycle check

- Status: fresh immutable-source retry prepared; not launched
- Created: 2026-10-11 01:49 PT
- Last updated: 2026-10-11 14:51 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Recorded: 2026-10-11 01:49 PT

Prove one complete, atomic Claude Opus 4.8 research → native data generation
→ proposal approval → real-GPU one-step training → merged-adapter vLLM
evaluation → score/finding lifecycle without loading or producing any
AutoData component or artifact. This gate validates execution and provenance;
its bounded score is not a scientific result.

## Context

Recorded: 2026-10-11 01:49 PT

This is the first ordered Run 16 gate before the five-chain topology check and
the full run. It follows Run 12's pattern of giving a substantial canary its
own configuration, thin shared-path launcher, stable specification, and
append-only progress record.

Two earlier attempts remain retained as incident evidence:

- [The first attempt stopped before research because of a sandbox-helper
  return-status bug](../../PROGRESS.md#run16-event-one-chain-startup-failure).
- [The second completed the functional lifecycle but was rejected because its
  source commit drifted during execution](../../PROGRESS.md#run16-event-one-chain-functional-pass-source-drift).

The fresh retry uses the [attempt-local immutable-source
repair](../../PROGRESS.md#run16-event-immutable-source-recovery). Neither prior
attempt is eligible as the prerequisite proof.

## Launch

Recorded: 2026-10-11 01:49 PT

After the model-role mapping below is explicitly confirmed, the exact commit
is synchronized to a clean HPC `autodata` worktree, the Gemma target endpoint
is healthy, and no Run 16 job is active, launch with:

```bash
experiments/dishonest_sycophancy_concealing/run_16/canary/one_chain_lifecycle_check/launch/launch.sh
```

## Plan

Recorded: 2026-10-11 01:49 PT

Launch one `canary` seed with one research session, a one-step PEFT training
job, and one one-GPU evaluator for exactly two `verbalized_ece` items. The
evaluator starts on demand only after the smoke proof passes and the pipeline
stages that exact adapter into the submission queue.

The launcher snapshots the selected commit into an attempt-local detached Git
repository with no remote or object alternates. Every scheduled stage must use
that immutable snapshot and record the same commit.

## Fixed contract

Recorded: 2026-10-11 14:51 PT

| Dimension            | One-chain contract                                      |
| -------------------- | ------------------------------------------------------- |
| Chain                | `canary`                                                |
| Research budget      | One started session; one required score/finding pair    |
| Research wall time   | Two hours                                               |
| Data generation      | Native researcher-authored method; AutoData disabled    |
| Training             | One real-GPU optimizer step; one lane; 15-minute limit  |
| Evaluation           | On demand; one GPU; one worker; one-hour limit          |
| Evaluation items     | Exactly two `verbalized_ece` items                      |
| Candidate serving    | Atomic merge; vLLM 0.25.1; language-model-only mode    |
| Candidate retention  | Retain source adapter and merge manifest                |
| Merged checkpoint    | Ephemeral; remove after evaluation                      |
| Source               | Detached attempt-local snapshot of one exact Git commit |
| Durable output root  | `/checkpoint/ram/aar/$USER/run16_native_generation`     |

## Model and execution roles

Recorded: 2026-10-11 01:49 PT

This canary uses native model-authored data generation. AutoData is disabled,
so there is no AutoData generator service, row judge, broker, workspace,
recipe, comparator, or production-export role.

```text
AAR control plane
├─ AAR researcher and native data-generation author
│  └─ Claude Opus 4.8, model claude-opus-4-8 at maximum effort
│     Meta Claude CLI with secure internet; no AAR Bubblewrap wrapper
├─ AAR proposal-approval monitor
│  └─ claude-4-8-opus through Meta Model API
│     Reviews method policy, reproducibility, leakage, and data provenance
├─ Optional native target probe
│  └─ Gemma 4 31B IT, served model gemma-4-31B-it
│     Serve API v2 deployment winnieyangwn-gemma-4-31B-it, thinking required
├─ AAR training model
│  └─ Gemma 4 31B IT fixed checkpoint + a new PEFT adapter
│     /checkpoint/ram/shared/models/google/gemma-4-31B-it
└─ AAR evaluator
   └─ Gemma 4 31B IT base + the canary's candidate adapter through vLLM
      Atomic merged checkpoint, vLLM 0.25.1, language-model-only mode
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
- The Claude preflight proves model `claude-opus-4-8`, maximum effort, secure
  internet mode, an executable CLI, and bounded paper search.
- The generated method has declared data provenance and passes proposal review,
  its real-GPU smoke, and adapter reload validation.
- The method, training proof, and attempt metadata record the same immutable
  submitted source commit.
- The on-demand evaluator retains vLLM 0.25.1, language-model-only,
  merged-checkpoint, and merge-manifest evidence, then removes the ephemeral
  merged checkpoint.
- Exactly two `verbalized_ece` items are evaluated, and one score plus exactly
  one matching result finding exist for the same run ID.
- No AutoData plugin, broker, workspace, state database, recipe execution, or
  production export exists in the attempt.
- `verify_run_16_canary.py` emits `metadata/canary_passed.json` with every
  required field true and `lifecycle_chain_count: 1`.

## Stop criteria

Recorded: 2026-10-11 01:49 PT

Stop on any AutoData initialization, missing provenance, source drift,
method-contract failure, invalid adapter, failed reload validation, evaluator
backend/version/merge-marker mismatch, evaluation-item mismatch, duplicate or
missing finding, or score/finding mismatch. Preserve the failed attempt and use
a fresh attempt for any retry.

## After a pass

Recorded: 2026-10-11 01:49 PT

Create the fail-closed lifecycle proof with:

```bash
python experiments/dishonest_sycophancy_concealing/run_16/canary/verify_run_16_canary.py \
  <one-chain-attempt>
```

Review `<one-chain-attempt>/metadata/canary_passed.json`, then supply that exact
proof to the five-chain topology gate. A one-chain pass does not directly
authorize the full run. Do not treat the bounded score as a scientific
conclusion.
