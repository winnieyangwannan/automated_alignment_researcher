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
│   ├── verify_run_14_canary.py
│   ├── one_chain_lifecycle_check/
│   │   ├── config/run.yaml
│   │   ├── launch/launch.sh
│   │   ├── README.md
│   │   └── PROGRESS.md
│   └── five_chain_lifecycle_check/
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

## Model and execution roles

- Researcher and native data-generation author: Kimi-K2.6, logical deployment
  `steerability_8-kimi26`, through the credential-hiding Serve API v2 bridge.
- Proposal monitor: `claude-4-8-opus` through Meta Model API.
- Training base and optional target probe: fixed Gemma 4 31B IT; training adds
  a new PEFT adapter locally, while target probing uses the shared endpoint.
- Evaluator inference: Gemma 4 31B IT plus each atomically merged candidate
  adapter through vLLM 0.25.1 in language-model-only mode.
- Evaluator judge: `gpt-5-6-luna` through Meta Model API for model-judged full
  benchmarks; the canaries use rule-scored `verbalized_ece` and make no judge
  model call.
- Trusted deterministic roles: AAR orchestration, transport, proposal-policy
  checks, benchmark rules, and score/finding joins. AutoData generator, row
  judge, broker, workspace, recipe, comparator, and production export roles do
  not exist in Run 14.

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

After it finishes, create and review its fail-closed proof:

```bash
python experiments/dishonest_sycophancy_concealing/run_14/canary/verify_run_14_canary.py \
  <one-chain-attempt>
```

Use that exact proof to launch the five-chain topology check:

```bash
experiments/dishonest_sycophancy_concealing/run_14/canary/five_chain_lifecycle_check/launch/launch.sh \
  <one-chain-attempt>/metadata/canary_passed.json
```

After five complete score/finding pairs produce a passed topology proof, launch
the full run:

```bash
experiments/dishonest_sycophancy_concealing/run_14/launch/submit_full.sh
```

The launchers print and retain the attempt directory and pipeline job ID.
`metadata/children.tsv` records one evaluator and one research-chain job per
seed for the full run. The five-chain topology gate instead launches five
research chains in one isolated team and one on-demand evaluator that drains
all five staged adapters.

## Isolation and provenance

Each seed owns a separate team directory, forum, method tree, chain memory,
submission queue, score directory, and evaluator. Attempts retain the resolved
YAML, exact source commit, baseline provenance, Kimi endpoint preflight,
evaluator runtime snapshot, and child job IDs. Held-out data remains outside
research-readable outputs.
