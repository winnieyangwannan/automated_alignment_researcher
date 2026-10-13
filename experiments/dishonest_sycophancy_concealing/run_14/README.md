# Run 14: v3 versus v2 recipe comparison

**Experiment code branch:** `autodata`

- Status: configured; recipe identity requires clarification; not launched
- Created: 2026-10-13 00:42 PT
- Time standard: Pacific Time (`America/Los_Angeles`)

## Goal

Compare whether the new v3 recipe with stronger grounding generates more
challenging, valid training data than the v2 recipe in Run 13 Canary Trial 14.
Keep every run-level model, budget, concurrency, partition, meta-iteration,
production and training setting identical.

## Context

Reference:
`experiments/dishonest_sycophancy_concealing/run_13/canary/trial_14/autodata_run.yaml`
at setup source commit `e17ab31781fc67edfaa8d19b160296340378cd13`.

This Run 14 replaces the deleted, unlaunched Opus 5 comparison package with a
recipe comparison using Opus 4.8 throughout. The only YAML changes will be the
isolated Run 14 identity and the exact recipe directory requested by the user:
`aar/autodata_recipes/dishonest_sycophancy_concealing`.

**Recipe identity caveat:** this requested directory currently contains the
older synthetic recipe (`aar.autodata.grounding-coverage/v2`), not the new
paper-grounded v3 work. That work is in `aar/autodata_recipes/v3_grounding`.
The YAML honors the explicit requested path pending the user's clarification;
do not label the resulting data as v3 or claim a v3-versus-v2 comparison until
the recipe content or path is resolved.

The alternative `v3_grounding` recipe is not currently launch compatible:
its rubric schema is `aar.autodata.paired-judge-rubric/v1`, which the AAR
compiler rejects; its manifest builder lacks the host-required `--count`
argument; and its own `grounding/pipeline_revision_plan.md` says the expanded
16-family grounding requires pipeline/scoring changes before execution.
These recipe changes are outside this run-configuration setup.

One `alpha` chain; one structural target pair; exactly ten meta iterations;
64 tuning, 32 validation and 32 test tasks; AutoData concurrency eight; five
provider attempts; three full-corpus finalization passes; 1,250 production
tasks; 1,000 accepted rows; stop after verified `training_smoke`. All time and
cost limits remain those of Trial 14.

## Model and execution roles

- Researcher and delegated proposal/approval monitor: Claude Opus 4.8,
  `claude-opus-4-8`, deployment `meta-claude-cli-opus-4-8`, Meta Claude CLI,
  maximum effort.
- AutoData semantic optimizer and generator/teacher/challenger: Claude Opus 4.8,
  `claude-4-8-opus`, deployment `meta-model-api-claude-4-8-opus`, Model API
  Responses.
- Row judge: `gpt-5-6-luna`, Model API Responses; no separate deployment ID.
- Target probe: `gemma-4-31B-it`, fixed base, Serve API v2 through Chat
  Completions. The logical deployment and checkpoint hash must be supplied and
  verified before launch; no new deployment is selected during setup.
- Training base: Gemma 4 31B IT at
  `/checkpoint/ram/shared/models/google/gemma-4-31B-it`, local GPU training,
  fixed base plus a new PEFT adapter; one verified optimizer step.
- Evaluator inference and evaluator judge: not used at the `training_smoke`
  boundary; no evaluator or held-out AAR score is part of this comparison.
- Orchestration, broker, lifecycle approvals, receipts, isolation and comparator:
  deterministic trusted code; AutoData revision
  `f53bc2136905461ffdbba0a203a12e351e184aaf`. The monitor reviews approval
  evidence; host code validates and signs the approved lifecycle transition.

All model roles match Run 13 Trial 14. No model calls have been made for Run 14.

## Launch

Before submission, confirm the complete model-role mapping and exact source
revision, as required by the `organize-aar-experiment` skill. Verify the
selected recipe's host compatibility and obtain the reviewed external
recovery manifest and compatible Opus 4.8/Gemma/Luna provider proof.

From the synchronized HPC `autodata` worktree:

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD"
export AAR_BENCHMARK_DOCS="$PWD/benchmark_docs"
export BENCHMARK_DOCS_DIR="$PWD/benchmark_docs"
AAR_RUN14_LIFECYCLE_COORDINATOR_COMMIT=<reviewed-run14-commit> \
AAR_RUN14_PREAUTODATA_RECOVERY_MANIFEST=<external-mode-600-run14-manifest> \
AAR_RUN14_CANARY_ROOT=<verified-opus48-gemma-luna-proof-root> \
AAR_RUN14_REUSE_BASE_DEPLOYMENT=<verified-gemma-deployment> \
AAR_RUN14_SECRET_ENV=<mode-600-secret-path> \
  experiments/dishonest_sycophancy_concealing/run_14/canary/v3_recipe_comparison/launch/launch.sh
```

The manifest must bind `run14` / `trial14` / `alpha` and idea UID
`run14-trial14-alpha-iteration-1`. It imports only the reviewed pre-AutoData
proposal. Create a fresh AutoData workspace, meta execution and production
export; preserve the original Trial 14 attempt and artifacts.

If a matching provider proof does not exist, the gate's
`launch/prepare_proof.sh preflight`, followed after a pass by
`launch/prepare_proof.sh canary <proof-root>`, uses the unchanged Opus 4.8 runtime
profile. These commands submit jobs and require separate launch authorization
and model-role confirmation.

## Pass criteria

- YAML leaf differences from Trial 14 are exactly `run_id` and `recipe_root`.
- All ten configured native meta iterations produce retained candidate decisions.
- Final test evidence meets the selected recipe's protected quality, challenge
  and validity gates; retain the metric and rubric identities.
- Production exports exactly 1,000 accepted rows from the 1,250 requested fresh
  tasks with authenticated provenance.
- AAR consumes the export, completes one Gemma optimizer step and verifies its
  consumption receipt and PEFT adapter.
- No evaluator launches and no hidden item-level evidence leaks.

Failure to reach production is a diagnostic outcome. Record it without
claiming lifecycle success or training results.

## Stop criteria

Stop before submission on unresolved recipe identity, missing model
confirmation, non-recipe YAML drift,
recipe/host incompatibility, uncommitted recipe dependencies, incompatible
provider proof, or a recovery identity mismatch. During execution, stop on
protected-file mutation, factual/teacher drift during pressure-only rewrites,
identity, budget, approval, provenance, export or training-contract violations,
hidden item leakage, or evaluator launch.

## Directory layout

```text
run_14/
├── README.md
├── PLAN.md
├── PROGRESS.md
└── canary/
    ├── README.md
    ├── launch/launch.sh
    ├── slurm/pipeline.sbatch
    ├── slurm/chain_controller.sbatch
    └── v3_recipe_comparison/
        ├── README.md
        ├── PROGRESS.md
        ├── config/run.yaml
        ├── launch/launch.sh
        ├── launch/prepare_proof.sh
        └── launch/verify_config.py
```

## Comparison record

Retain candidate strategy diffs and per-iteration aggregate teacher quality,
challenge, validity, utility and accepted-row yield. Record first-attempt and
finalization outcomes, feedback conversion rates, rejection reasons, time,
model calls and cost. Join them to the source commit, resolved configuration,
source hashes, split/task seeds, rubric/comparator identity and target binding.

Use the actual Trial 14 v2 attempt as the comparator; do not substitute an
older Trial 13 outcome. Report any absent completed v2 reference explicitly.
Keep internal hidden-validation/test item details private.

If v3 changes the challenge definition, rubric, task family coverage, or target
call count, disclose those recipe changes. Raw v2 and v3 challenge/utility
numbers then measure different quantities; use common target-failure and
accepted-row definitions for a scientific ranking, or report the native
results as diagnostic evidence. A recipe-wide comparison does not isolate
source quality from other recipe changes.

## Validation and deployment state

The requested-path YAML passed strict loading, runtime compilation and artifact
validation, and native recipe staging with 128 generated partition tasks.
The existing Run 14 contracts and selected shared-fence/configuration checks
passed: 14 tests. Shell syntax, ShellCheck error checks, and focused Ruff checks
passed. No inference was performed.

The focused setup is local to the devserver. HPC synchronization is deferred
because active training jobs use the execution checkout directly; see
[the operational record](PROGRESS.md#run14-config-validated).

Offline operator check (from the repository root):

```bash
PYTHONPATH="$PWD" .venv/bin/python \
  experiments/dishonest_sycophancy_concealing/run_14/canary/v3_recipe_comparison/launch/verify_config.py
```
