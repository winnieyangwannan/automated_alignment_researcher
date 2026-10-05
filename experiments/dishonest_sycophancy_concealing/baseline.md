# Three-dimensional baseline evaluation

Status: implementation ready; concealing-uncertainty source baseline and final
composed baseline still require live execution.

## Fixed evaluation profile

| Field                    | Value                                                 |
| ------------------------ | ----------------------------------------------------- |
| HPC cluster              | `fair-cw-use2-1`                                      |
| Execution worktree       | `/storage/home/winnieyangwn/aar-worktrees/uv`         |
| Git branch               | `uv`                                                  |
| Target identity          | `google/gemma-4-31B-it`                               |
| Target checkpoint        | `/checkpoint/ram/shared/models/google/gemma-4-31B-it` |
| Judge backend            | FAIR Model API                                        |
| Judge model              | `gpt-5-6-luna`                                        |
| Target thinking          | enabled                                               |
| Thinking plus answer cap | `8192` tokens                                         |
| Evaluation batch size    | `2`                                                   |
| Concealing source GPUs   | `4` (one replica per benchmark)                       |
| Final composed GPUs      | `2`                                                   |

Source baselines can be reused only when the scoring-affecting profile fields
match. Their Git commits and GPU concurrency may differ and are recorded
separately. The final composed baseline must match the final launch commit.

## Complete 13-entry roster

| Dimension               | Benchmark               | Role            | Source action |
| ----------------------- | ----------------------- | --------------- | ------------- |
| Honesty                 | `mask_factual`          | Hill climb      | Reuse         |
| Honesty                 | `mask_continuation`     | Hill climb      | Reuse         |
| Honesty                 | `mask_disinformation`   | Hill climb      | Reuse         |
| Honesty                 | `deceptionbench_reward` | Held-out        | Reuse         |
| Sycophancy              | `sycophancy_eval`       | Hill climb      | Reuse         |
| Sycophancy              | `sycon_fp`              | Held-out        | Reuse         |
| Concealing uncertainty  | `llm_uncertainty_bench` | Hill climb      | Run           |
| Concealing uncertainty  | `verbalized_ece`        | Hill climb      | Run           |
| Concealing uncertainty  | `abstentionbench`       | Hill climb      | Run           |
| Concealing uncertainty  | `sciq_uncertainty`      | Held-out        | Run           |
| Shared                  | `mmlu`                  | Capability gate | Reuse         |
| Shared                  | `gsm8k`                 | Capability gate | Reuse         |
| Shared                  | `ifeval`                | Capability gate | Reuse         |

The dedicated new source job contains only the four concealment benchmarks. It
does not rerun honesty, sycophancy, or shared capability entries.

## Incremental procedure

1. Locate the retained complete honesty and sycophancy private results and
   manifests. Do not use partial or timed-out artifacts.
2. Submit only the new source baseline:

   ```bash
   cd /storage/home/winnieyangwn/aar-worktrees/uv
   source .venv/bin/activate
   export PYTHONPATH="$PWD"
   replication/submit_concealing_multidimensional_baseline.sh
   ```

3. After it completes, merge the three profile-compatible sources:

   ```bash
   python replication/record_multidimensional_baseline.py \
     --syc-result <syc-private-result.json> \
     --honesty-result <honesty-private-result.json> \
     --concealing-result <concealing-private-result.json> \
     --syc-manifest <syc-manifest.json> \
     --honesty-manifest <honesty-manifest.json> \
     --concealing-manifest <concealing-manifest.json> \
     --output <provisional-13-entry-override.json>
   ```

4. Submit the final-commit composed baseline:

   ```bash
   replication/submit_multidimensional_baseline.sh \
     <provisional-13-entry-override.json>
   ```

5. Validate the full private result, record the canonical baseline and manifest,
   and run `replication/preflight_multidimensional.py --launch` before AAR.

The final composed run evaluates all 13 entries once. That is required to
establish one final-commit canonical baseline; it is distinct from rerunning the
old dimension-specific source jobs.

## Result handling

- `baseline_results/baseline.research.json` excludes all three held-outs.
- `baseline_results/private/baseline.research.json` contains the evaluator-only
  full result.
- Use raw `per_benchmark` means, confidence intervals, counts, and decomposition
  from completed results. Initial `headline_pct` and `closed_pct` values are not
  calibrated until the fixed baselines are republished.
- Never copy held-out means, intervals, item data, or derived values into AAR
  prompts, forums, logs, or research-readable result files.

## Historical invalid attempts

The earlier sycophancy and honesty attempts documented below remain diagnostic
only and must not be merged:

- `1660478`: 50/200 truncated sycophancy generations.
- `1660776`: hard-coded short MASK generation limits.
- `1663879`: timed out before atomic result publication.
- `1663885`: timed out before atomic result publication.
- `1673380`: shell wrapper failed before model loading.

Later retained honesty/sycophancy results are valid inputs only if their
manifests pass the exact profile contract above and every expected benchmark has
`n > 0` with a valid confidence interval.

## Completion checks

- All source jobs end successfully with atomic private results.
- The three source profiles match even when their Git commits differ.
- The merged provisional map has exactly 13 unique entries.
- The final composed result has exactly seven safety, three held-out, and three
  capability entries.
- Truncation, allocator, CUDA, judge, and count health gates pass.
- The canonical baseline and manifest match the launch commit and target model.
