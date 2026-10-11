# Run 14: native model-authored data generation

**Experiment code branch:** `autodata`

Run 14's launchers and scheduled payload require this branch.

- Status: full five-chain 5×50 run paused for source hardening and recovery
- Last updated: 2026-10-11 00:03 PT

## Goal

Run five independent Kimi AAR research chains to 50 successful score/finding
pairs per chain (250 total), with a ceiling of 60 research sessions per chain.
Each researcher authors its own reproducible training-data generation without
AutoData.

## Context

Run 14 preserves Run 12's Kimi researcher, five independent chains, Gemma-4
training/evaluation stack, and proposal/evaluation isolation. Its intentional
workflow change is that AutoData is disabled. Each research model writes and
validates the data-generation logic inside its normal method package.

Scale-up is ordered and fail-closed:

```text
one-chain lifecycle proof
  → five-chain topology lifecycle proof
  → full five-chain 5×50 run
```

The one-chain gate passed. The first five-chain topology attempt stopped
without a proof after proposal and training failures. The corrected five-chain
canary subsequently passed, and its proof authorized the active full run.

## Directory layout

```text
run_14/
├── config/run.yaml
├── launch/submit_full.sh
├── recovery/
│   ├── finalize_scored_run.py
│   └── finalize_scored_run.sh
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
| Target per chain | 50 atomic score/result pairs                      |
| Session ceiling  | 60 sessions per chain                             |
| Training         | One decoupled GPU lane per isolated chain         |
| Evaluation       | One four-GPU vLLM evaluator per isolated chain    |
| Data generation  | Native method code authored by the research model |
| AutoData         | Disabled and rejected if re-enabled               |

## Launch

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

After five complete score/finding pairs produce a passed topology proof, pass
both exact proof files to the full launcher:

```bash
experiments/dishonest_sycophancy_concealing/run_14/launch/submit_full.sh \
  <one-chain-attempt>/metadata/canary_passed.json \
  <five-chain-attempt>/metadata/canary_passed.json
```

The full launcher validates both proofs, verifies that the five-chain proof is
bound to the exact one-chain proof by SHA-256, copies both proofs into the new
attempt, and records their hashes before submission. A command in this README
is not launch authorization; reconfirm the documented model-role mapping before
starting a new canary, continuation, recovery, or full attempt.

The launchers print and retain the attempt directory and pipeline job ID.
`metadata/children.tsv` records one evaluator and one research-chain job per
seed for the full run. The five-chain topology gate instead launches five
research chains in one isolated team and one on-demand evaluator that drains
all five staged adapters.

If a one-chain canary has an approved proposal and authoritative public score
but its Kimi session stops before the required `share_finding` call, recover
only that missing publication step:

```bash
experiments/dishonest_sycophancy_concealing/run_14/recovery/finalize_scored_run.sh \
  <one-chain-attempt>
```

The recovery validates the retained approval and score, keeps AutoData
disabled, forbids method edits, training, and evaluation, and succeeds only
after exactly one finding is durably joined to the scored run ID.

## Pass criteria

- The one-chain proof passes all lifecycle checks.
- A corrected five-chain proof passes for all five configured seeds and retains
  the SHA-256 of the exact one-chain proof it consumed.
- Full-attempt metadata retains the resolved YAML, both ordered proof files,
  their hashes, the source commit, and five distinct research/evaluator job
  pairs.
- Each chain publishes 50 complete score/finding pairs joined by run ID; the
  full run therefore produces 250 complete pairs. Started or failed sessions do
  not count toward this target.
- Each chain stays within its 60-session ceiling.
- Every counted result has a source-bound training receipt and the required
  fail-closed vLLM runtime and merged-adapter provenance.
- Attempt metadata proves native generation and `AAR_AUTODATA=0`, with no
  AutoData process or artifact.

## Stop criteria

Stop before scale-up or submission if either ordered proof is missing, failed,
stale, or not bound to the other; if the model-role mapping is unconfirmed; if
the worktree is dirty or not at the retained source commit; or if baseline,
public-source, endpoint, runtime, secret, or storage validation fails.

During execution, stop or use a state-preserving recovery if AutoData is
initialized, evaluator-only data reaches a research process, proposal or method
contracts are bypassed, a training/evaluator failure is not durably structured,
child job identities are incomplete, or score/finding joins cannot be proven.

## Monitoring and recovery

Use retained metadata rather than guessing job identities:

```bash
column -t -s $'\t' <attempt>/metadata/children.tsv
squeue -j <pipeline-and-child-job-ids> -o '%.18i %.30j %.10T %.10M %R'
sacct -j <pipeline-and-child-job-ids> --format=JobID,JobName,State,ExitCode,Elapsed
```

Track complete score/finding joins by run ID and append durable state changes to
`PROGRESS.md` in PT. The existing finding-only recovery is deliberately narrow;
it is not a general full-chain resume command. A full-run recovery must preserve
existing results, reject duplicate active jobs, and subtract already-started
sessions from each chain's 60-session budget.

### Evaluator-throughput monitoring goal

Recorded: 2026-10-10 23:41 PT

The recovery configuration sets `evaluation.vllm_log_stats: true`. The compiled
runtime must emit `EVAL_VLLM_LOG_STATS=1`, and each successfully initialized
vLLM replica must log both `log_stats=True` and `disable_log_stats=False` before
its periodic scheduler statistics are accepted as active telemetry.

Determine whether the full evaluator's target-model batch size of `2` is too
conservative. Run a separately authorized, public-only throughput canary with
the same candidate checkpoint, four-GPU evaluator topology, vLLM 0.25.1 engine
settings, decoding settings, benchmark ordering, judge backend, and judge
concurrency. Compare batch sizes `2`, `4`, and `8`; test a larger batch only
when the preceding size has measured GPU and memory headroom. Do not change the
active full run.

Retain held-out-safe measurements for every batch size and benchmark:

- end-to-end evaluation wall time, model-load time, benchmark queue time, and
  per-benchmark wall time;
- completed examples per second, prompt tokens per second, output tokens per
  second, and total tokens per second, separating prefill and decode when vLLM
  exposes both;
- request latency and time to first token at median, p95, and p99, plus active,
  queued, and completed request counts;
- GPU SM utilization, HBM allocation and peak use, KV-cache utilization,
  effective batch occupancy, and allocator or out-of-memory warnings;
- generated and truncated completion counts, output-token distributions,
  parse failures, evaluator retries, and terminal scoring errors;
- Model API judge request rate, completed calls, median/p95/p99 latency,
  retry-after time, HTTP 429/rate-limit events, 5xx errors, timeouts, and
  connection resets; and
- aggregate score and capability-gate parity, without retaining raw held-out
  prompts, responses, item-level scores, or hidden benchmark scores.

Separate cold model loading from steady-state scoring and repeat measurements
enough to distinguish stable throughput from noise. A larger batch is eligible
only when it produces a repeatable throughput or wall-time improvement without
OOMs, allocator warnings, excess truncation, provider-rate-limit pressure,
terminal errors, or material score/capability drift.

Because sampled generation can depend on batch composition and floating-point
execution order, changing only the candidate evaluator batch is forbidden. Any
adopted batch size must have a matching validated baseline protocol or a
separate parity proof. The monitor must conclude with one decision: retain
batch `2`, adopt the highest validated batch for a future run, or collect more
evidence. It must identify the measured bottleneck as target generation, model
loading, judge/API latency, scheduler queueing, or another observed stage.

## Isolation and provenance

Each seed owns a separate team directory, forum, method tree, chain memory,
submission queue, score directory, and evaluator. Attempts retain the resolved
YAML, exact source commit, baseline provenance, Kimi endpoint preflight,
evaluator runtime snapshot, and child job IDs. Held-out data remains outside
research-readable outputs.
