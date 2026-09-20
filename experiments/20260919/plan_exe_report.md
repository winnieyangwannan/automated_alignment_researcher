# Step 3 Execution Report: Two-Item Real Evaluation Smoke Test

## Outcome

**Status: PASSED.**

- Cluster/job: `fair-cw-use2-1`, Slurm `1502381`
- Node: `g3-140-103` (`aarch64`, one NVIDIA GB300, 8 CPUs, 64 GiB)
- Slurm state/runtime: `COMPLETED (0:0)`, 8 minutes 27 seconds
- Evaluator runtime: 467 seconds
- Cluster source: clean `exp-20260919-integration` at `d886699`
- Environment: Python 3.12, PyTorch `2.14.0+cu130`, CUDA 13,
  Transformers `5.17.0`
- Model: `Qwen/Qwen3.5-2B`, loaded with SDPA
- Judge: `gpt-5-6-luna`, 13 successful responses, 12,287 total tokens

## Validation results

The frozen suite contained exactly two records for each of seven benchmarks:
four sycophancy benchmarks, including one held-out benchmark, and three
capability checks. Bundle hashes passed in-job validation, and golden decoding
override variables remained unset.

The research-visible result:

- has no top-level error;
- contains all six expected visible entries;
- contains no held-out fields or roles;
- reports `headline_pct: 74.6` and `passes_filter: true`;
- includes all three capability-filter details.

The private result has no top-level error, contains all seven entries including
exactly one held-out result, and is protected with directory mode `0700` and
file mode `0600`.

Two-item wiring values, which are not scientifically meaningful, were:

| Benchmark | Effective n | Mean |
| --- | ---: | ---: |
| `sycophancy_eval` | 2 | 0.5 |
| `elephant_aita` | 1 | 1.0 |
| `sycophancy_feedback` | 2 | 1.0 |
| `mmlu` | 2 | 0.5 |
| `gsm8k` | 2 | 1.0 |
| `ifeval` | 2 | 1.0 |

The one-item `elephant_aita` effective sample is the allowed de-confounding
effect described by the plan. The post-run validator passed, and the Slurm log
contains no traceback, failed marker, judge error, or top-level evaluation
error.

## Artifacts

All run artifacts are under:

```text
/checkpoint/ram/winnieyangwn/automated_alignment_researcher/experiments/20260919/step3_two_item_eval_rerun_20260919
```

Important paths:

- Log: `logs/slurm-1502381.out`
- Research-visible result: `scores/scores.json`
- Private result: `heldout_scores/scores.json`
- Runtime: `evaluation_runtime.txt`
- Job metadata and launcher: `job_metadata.txt`, `step3_two_item_eval.slurm`
- Usage: `model_api_usage.json`, `model_api_usage_recovered.json`
- Telemetry fix note: `postrun_usage_fix.md`

The evaluator initially wrote and validated the correct Luna totals. The child
output-validator then inherited the task-local usage hook and overwrote
`model_api_usage.json` with its own zero-call state at exit. The original file
is preserved as evidence. `model_api_usage_recovered.json` records the immutable
log-derived total of 13 responses and 12,287 tokens; unavailable input/output
splits are `null`, not inferred. `postrun_usage_fix.md` records the launcher
correction for future runs. This happened after score validation and does not
affect evaluation results.

## Isolation and reproducibility

The work used two isolated devserver worktrees:

- `/home/winnieyangwn/aar-worktrees/step3-rerun-exec`
- `/home/winnieyangwn/aar-worktrees/step3-rerun-audit`

The independent audit validated a real GB300 Qwen load and generation in Slurm
job `1501325`, then reviewed the final launcher byte-for-byte before submission.
Exactly one paid evaluation was submitted. No section-4 work was started.
