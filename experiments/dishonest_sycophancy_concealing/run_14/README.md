# Run 14: native model-authored data generation

**Experiment code branch:** `autodata`

Run 14's launchers and scheduled payload require this branch.

Run 14 preserves Run 12's Kimi researcher, five independent chains, Gemma-4
training/evaluation stack, and target of five durable score/result pairs per
chain. Its only intentional workflow change is that AutoData is disabled. Each
research model writes and validates the data-generation logic inside its normal
method package.

## Directory layout

```text
run_14/
├── config/run.yaml
├── launch/submit_full.sh
├── slurm/pipeline.sbatch
├── canary/
│   ├── README.md
│   └── one_chain_lifecycle_check/
│       ├── config/run.yaml
│       ├── launch/launch.sh
│       ├── README.md
│       └── PROGRESS.md
├── README.md
├── PLAN.md
└── PROGRESS.md
```

## Configuration and invariants

The authoritative switch is declarative:

```yaml
data_generation:
  backend: native
```

The validated config loader emits `AAR_AUTODATA=0`. Both the login-node
launcher and scheduled pipeline re-read the YAML, require that value, and clear
inherited `AAR_AUTODATA_*` variables. Run 14 does not resolve an AutoData
checkout, load its plugin, start a broker, compile a recipe, create a workspace,
or require an AutoData production export.

The ordinary AAR method contract remains active. Kimi may author reproducible
synthetic, programmatic, templated, target-model-generated, or declared external
teacher data. The proposal monitor still verifies provenance and rejects use or
imitation of evaluation data. The shared Gemma Serve API v2 endpoint remains
available for optional target-model generation.

## Topology

| Component        | Run 14 policy                                     |
| ---------------- | ------------------------------------------------- |
| Research model   | Kimi-K2.6                                         |
| Chains           | `alpha`, `beta`, `gamma`, `delta`, `epsilon`      |
| Target per chain | Five atomic score/result pairs                    |
| Session ceiling  | Eight sessions per chain                          |
| Training         | One decoupled GPU lane per isolated chain         |
| Evaluation       | One four-GPU vLLM evaluator per isolated chain    |
| Data generation  | Native method code authored by the research model |
| AutoData         | Disabled and rejected if re-enabled               |

## Launch sequence

First run the bounded one-chain lifecycle check from the synchronized HPC
`autodata` worktree:

```bash
experiments/dishonest_sycophancy_concealing/run_14/canary/one_chain_lifecycle_check/launch/launch.sh
```

After reviewing its complete score/finding pair and held-out-safe evidence,
launch the full run:

```bash
experiments/dishonest_sycophancy_concealing/run_14/launch/submit_full.sh
```

The launcher prints and retains the attempt directory and pipeline job ID.
`metadata/children.tsv` records one evaluator and one research-chain job per
seed after the scheduled launcher completes.

## Isolation and provenance

Each seed owns a separate team directory, forum, method tree, chain memory,
submission queue, score directory, and evaluator. Attempts retain the resolved
YAML, exact source commit, baseline provenance, Kimi endpoint preflight,
evaluator runtime snapshot, and child job IDs. Held-out data remains outside
research-readable outputs.
