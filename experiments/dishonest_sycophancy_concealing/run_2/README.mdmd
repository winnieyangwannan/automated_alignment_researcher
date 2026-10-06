# Run 2: five parallel three-axis research agents

Run 2 is a fresh AAR team for jointly improving honesty, sycophancy resistance,
and honest communication of uncertainty in `google/gemma-4-31B-it`. It reuses
the retained compatible 13-benchmark baseline and completed schema-v2 literature
manifest. It does not rerun either prerequisite.

## Topology and budget

Five Claude Opus 4.8 research chains (`alpha` through `epsilon`) start together,
share one fresh forum/leaderboard, and each has exactly one session in which to
produce one genuine trained candidate and publish its evaluated result finding.
Each chain has a hard USD 100 Agent SDK session budget, so their combined Claude
ceiling is USD 500. GPT-5.6 Luna judge use has a separate USD 500 authorized cap.

Training has five dependency lanes and may therefore use five one-GPU jobs at
once when Slurm capacity permits. One four-GB300 evaluator drains candidate
submissions in arrival order. It uses a dynamic queue across the 13 benchmarks
within each candidate evaluation. The evaluator and research chains have a
seven-day wall-time envelope, enough for roughly five serial 14-hour candidate
evaluations. A chain waiting for its score uses the long-lived score wait rather
than spending repeated agent turns.

| Component             | Run-2 configuration                                                                    |
| --------------------- | -------------------------------------------------------------------------------------- |
| Research agents       | Five concurrent chains: `alpha`, `beta`, `gamma`, `delta`, `epsilon`                    |
| Agent model           | `claude-opus-4-8`, maximum effort                                                       |
| Sessions              | One per chain; five total                                                               |
| Target model          | `google/gemma-4-31B-it`, trained as PEFT LoRA adapters                                  |
| Claude cap            | USD 100 per chain; USD 500 total                                                        |
| Judge                 | FAIR Model API, `gpt-5-6-luna`; separate USD 500 cap                                   |
| Integrity monitor     | FAIR Model API, `claude-4-8-opus`                                                       |
| Training parallelism  | Up to five one-GPU jobs                                                                |
| Evaluation            | One evaluator, four GB300 GPUs, dynamic per-benchmark queue; candidates handled serially |
| Shared state          | Fresh run-2 forum and leaderboard; no findings copied from run 1                        |
| Team ID               | `honesty-sycophancy-concealing-gemma4_31b-opus48-fiveparallel-run2-v0`                  |

## Evaluation suite

The research-visible hill-climb benchmarks are `mask_factual`,
`mask_continuation`, `mask_disinformation`, `sycophancy_eval`,
`llm_uncertainty_bench`, `verbalized_ece`, and `abstentionbench`. Capability
preservation gates use `mmlu`, `gsm8k`, and `ifeval`. Three composition-specific
checks are evaluator-only generalization tests. Their private item data and
scores must not be copied into research-visible files or this document.

Scoring remains the equal-dimension, coverage-weighted geometric mean with a
per-optimized-benchmark safety regression gate and capability regression gates.
Run 2 does not weaken or alter those rules.

## Paths

Retained prerequisite attempt:

```text
/checkpoint/ram/aar/winnieyangwn/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse
```

Run-2 team root:

```text
/checkpoint/ram/aar/winnieyangwn/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/aar_teams/honesty-sycophancy-concealing-gemma4_31b-opus48-fiveparallel-run2-v0
```

Within the team root, `methods/` contains generated methods, `_train/` and
`submissions/` contain retained adapters, `scores/` contains atomic
research-visible scores, `forum/` contains findings, `logs/` contains research
and training logs, and `_eval_private/` is evaluator-private state.

Launch provenance is retained under the attempt's `metadata/` directory:

```text
launch_run2_five_parallel_submission.txt
manifest-five-parallel.json
```

## Launch

The launcher is fail-closed and idempotent. A completely recorded prior launch
is reported without resubmission; partial state stops for operator repair so it
cannot duplicate GPU or judge spend.

From the HPC execution checkout:

```bash
cd /storage/home/winnieyangwn/aar-worktrees/uv
source .venv/bin/activate
export PYTHONPATH="$PWD"
export AAR_BENCHMARK_DOCS="$PWD/benchmark_docs"
export BENCHMARK_DOCS_DIR="$PWD/benchmark_docs"

bash experiments/dishonest_sycophancy_concealing/run_2/launch_run_2.sh \
  /checkpoint/ram/aar/winnieyangwn/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/attempt.env
```

## Monitoring

Define the team path:

```bash
TEAM=/checkpoint/ram/aar/winnieyangwn/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/aar_teams/honesty-sycophancy-concealing-gemma4_31b-opus48-fiveparallel-run2-v0
```

Read the exact evaluator and five chain job IDs from the retained launch record:

```bash
cat /checkpoint/ram/aar/winnieyangwn/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/metadata/launch_run2_five_parallel_submission.txt
```

Inspect live and terminal Slurm state:

```bash
squeue -n 'aar-eval-honesty_sycophancy_concealing_uncertainty,aar-honesty_sycophancy_concealing_uncertainty-gemma4_31b-alpha,aar-honesty_sycophancy_concealing_uncertainty-gemma4_31b-beta,aar-honesty_sycophancy_concealing_uncertainty-gemma4_31b-gamma,aar-honesty_sycophancy_concealing_uncertainty-gemma4_31b-delta,aar-honesty_sycophancy_concealing_uncertainty-gemma4_31b-epsilon' \
  -o '%.18i %.55j %.10T %.12M %R'

sacct -X -S 2026-10-05 -o JobID,JobName%55,State,Start,End,Elapsed,AllocTRES%80 -P
```

Follow all five public chain logs and list candidate progress:

```bash
tail -F "$TEAM"/logs/aar-honesty_sycophancy_concealing_uncertainty-gemma4_31b-*.out

find "$TEAM/submissions" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
find "$TEAM/scores" -maxdepth 1 -type f -name '*.json' -printf '%f\n' | sort
grep -l '"finding_type": "result"' "$TEAM"/forum/*.json 2>/dev/null | sort
```

A chain counts as successful only when its run ID has both an atomic
`scores/<run_id>.json` and a result finding in `forum/`. A completed agent
process or a staged adapter alone is not a completed result. Before repairing a
failure, check the session claim, training job, submission claim, score, and
finding so the same candidate is resumed rather than duplicated.

## Validity caveat

This run sets `AAR_FUNCTIONAL_SMOKE=1` because a separate evaluator Unix
principal is not provisioned. Code and path discipline hide evaluator config
and private outputs from the research prompt, but kernel-level user isolation is
absent. The run is valid for orchestration and research-visible hill climbing;
its private held-out results must not be presented as independently isolated
scientific generalization evidence.
