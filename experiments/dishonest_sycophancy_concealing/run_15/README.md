# Run 15: native model-authored data generation

**Experiment code branch:** `autodata`

Run 15's launchers and scheduled payload require this branch.

- Status: direct full launch authorized; exact source preparing for HPC launch
- Created: 2026-10-11 01:43 PT
- Last updated: 2026-10-11 03:07 PT

## Goal

Run five independent Kimi AAR research chains to 50 successful score/finding
pairs per chain (250 total), with a ceiling of 60 research sessions per chain.
Each researcher authors its own reproducible training-data generation without
AutoData.

## Context

Run 15 is a fresh-state successor to Run 14. It preserves Run 14's Kimi
researcher, five independent chains, Gemma-4 training/evaluation stack,
proposal/evaluation isolation, and native data-generation policy. It does not
import Run 14 sessions, proposals, adapters, scores, findings, or session
budgets.

Run 14 demonstrated that its retained attempt could no longer reach 50 pairs
within the 60-session ceilings for Alpha or Beta. Run 15 therefore starts only
after the reusable failure-feedback, proposal-revision, and one-shot recovery
fixes are committed, synchronized, and tested. Run 14 artifacts remain retained
as incident evidence.

The reusable default scale-up remains ordered and fail-closed:

```text
one-chain lifecycle proof
  → five-chain topology lifecycle proof
  → full five-chain 5×50 run
```

The user explicitly authorized this full 5x50 attempt to bypass both lifecycle
proofs after the replacement Kimi endpoint and all other launch dependencies
passed fresh preflight. The launcher requires an exact, conspicuous bypass
flag and retains a commit-bound override record. This exception does not weaken
the proof-gated default for future submissions. Run 14 proof files remain
historical evidence, not authorization for this fresh attempt.

## Directory layout

```text
run_15/
├── config/run.yaml
├── launch/submit_full.sh
├── recovery/
│   ├── finalize_scored_run.py
│   └── finalize_scored_run.sh
├── slurm/pipeline.sbatch
├── canary/
│   ├── README.md
│   ├── verify_run_15_canary.py
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
inherited `AAR_AUTODATA_*` variables. Run 15 does not resolve an AutoData
checkout, load its plugin, start a broker, compile a recipe, create a workspace,
or require an AutoData production export.

The ordinary AAR method contract remains active. Kimi may author reproducible
synthetic, programmatic, templated, target-model-generated, or declared external
teacher data. The proposal monitor still verifies provenance and rejects use or
imitation of evaluation data. The shared Gemma Serve API v2 endpoint remains
available for optional target-model generation.

`data_generation.max_sequential_target_generations: 256` is a deterministic
fail-fast bound for synchronous target-model generation. Generated methods must
make repeated target calls inside statically bounded loops; an unbounded loop or
a static product above 256 fails the method contract before GPU submission.

## Model and execution roles

- Researcher and native data-generation author: Kimi-K2.6, logical deployment
  `autodata2_8-kimi26`, through the credential-hiding Serve API v2 bridge;
  Kimi's optional thinking mode is disabled for the agent harness.
- Proposal monitor: `claude-4-8-opus` through Meta Model API.
- Training base and optional target probe: fixed Gemma 4 31B IT at
  `/checkpoint/ram/shared/models/google/gemma-4-31B-it`; training adds a new
  PEFT adapter locally, while target probing uses logical Serve API v2 model
  `gemma-4-31B-it` with thinking required.
- Evaluator inference: Gemma 4 31B IT plus each atomically merged candidate
  adapter through vLLM 0.25.1 in language-model-only mode.
- Evaluator judge: `gpt-5-6-luna` through Meta Model API for model-judged full
  benchmarks; the canaries use rule-scored `verbalized_ece` and make no judge
  model call.
- Trusted deterministic roles: AAR orchestration, transport, proposal-policy
  checks, benchmark rules, and score/finding joins. AutoData generator, row
  judge, broker, workspace, recipe, comparator, and production export roles do
  not exist in Run 15.

The user confirmed the 5x50/60-session topology at 2026-10-11 01:45 PT and
permanently replaced the Run 15 Kimi deployment with `autodata2_8-kimi26` at
2026-10-11 03:07 PT. Any subsequent model, deployment, checkpoint, adapter
mode, backend, or role change requires a new confirmation before submission.

## Topology

| Component        | Run 15 policy                                     |
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
experiments/dishonest_sycophancy_concealing/run_15/canary/one_chain_lifecycle_check/launch/launch.sh
```

After it finishes, create and review its fail-closed proof:

```bash
python experiments/dishonest_sycophancy_concealing/run_15/canary/verify_run_15_canary.py \
  <one-chain-attempt>
```

Use that exact proof to launch the five-chain topology check:

```bash
experiments/dishonest_sycophancy_concealing/run_15/canary/five_chain_lifecycle_check/launch/launch.sh \
  <one-chain-attempt>/metadata/canary_passed.json
```

After five complete score/finding pairs produce a passed topology proof, pass
both exact proof files to the full launcher:

```bash
experiments/dishonest_sycophancy_concealing/run_15/launch/submit_full.sh \
  <one-chain-attempt>/metadata/canary_passed.json \
  <five-chain-attempt>/metadata/canary_passed.json
```

For the explicitly authorized direct full attempt, use the narrow override:

```bash
experiments/dishonest_sycophancy_concealing/run_15/launch/submit_full.sh \
  --user-authorized-without-lifecycle-proofs
```

The full launcher validates both proofs, verifies that the five-chain proof is
bound to the exact one-chain proof by SHA-256, copies both proofs into the new
attempt, and records their hashes before submission. Under the explicit bypass,
it instead records the user-authorized scope, source commit, replacement Kimi
deployment, skipped proofs, and retained safety checks in mode-400 attempt
metadata. Before endpoint preflight or `sbatch`, every canary and full launch clones the clean submitted commit into
`<attempt>/runtime/aar-source` as a detached, remote-free, independent Git
snapshot. The scheduled pipeline and all child jobs use that attempt-local
source, config, benchmark documentation, and Python import root. Later progress
or documentation commits in the shared HPC worktree therefore cannot mutate an
active attempt. A command in this README is not launch authorization; reconfirm
the documented model-role mapping before starting a new canary, continuation,
recovery, or full attempt.

The launchers print and retain the attempt directory and pipeline job ID.
`metadata/children.tsv` records one evaluator and one research-chain job per
seed for the full run. The five-chain topology gate instead launches five
research chains in one isolated team and one on-demand evaluator that drains
all five staged adapters.

If a one-chain canary has an approved proposal and authoritative public score
but its Kimi session stops before the required `share_finding` call, recover
only that missing publication step:

```bash
experiments/dishonest_sycophancy_concealing/run_15/recovery/finalize_scored_run.sh \
  <one-chain-attempt>
```

The recovery validates the retained approval and score, keeps AutoData
disabled, forbids method edits, training, and evaluation, and succeeds only
after exactly one finding is durably joined to the scored run ID.

## Pass criteria

- Full-attempt metadata retains either both valid ordered proof files and their
  hashes or the exact commit-bound user-authorization override record.
- Full-attempt metadata also retains the resolved YAML, source commit, immutable
  source-snapshot root and manifest hash, and five distinct
  research/evaluator job pairs.
- Each chain publishes 50 complete score/finding pairs joined by run ID; the
  full run therefore produces 250 complete pairs. Started or failed sessions do
  not count toward this target.
- Each chain stays within its 60-session ceiling.
- Every counted result has a source-bound training receipt and the required
  fail-closed vLLM runtime and merged-adapter provenance.
- Attempt metadata proves native generation and `AAR_AUTODATA=0`, with no
  AutoData process or artifact.

## Stop criteria

Stop before scale-up or submission if neither valid ordered proofs nor the exact
explicit user-authorized override is present; if the model-role mapping is
unconfirmed; if
the worktree is dirty or not at the retained source commit; if the attempt-local
source is not detached, exact-commit, remote-free, independent, and clean; or if
baseline, public-source, endpoint, runtime, secret, or storage validation fails.

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
when the preceding size has measured GPU and memory headroom. Do not alter a
scientific attempt while collecting this separate performance evidence.

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
YAML, exact source commit, `metadata/source-snapshots.json` and its SHA-256,
attempt-local public sources and baseline inputs, Kimi endpoint preflight,
evaluator runtime snapshot, and child job IDs. The launch-time checkout is used
only to validate and create the snapshot; active jobs never execute from that
moving checkout. Held-out data remains outside research-readable outputs.
