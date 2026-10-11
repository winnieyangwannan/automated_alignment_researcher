#!/bin/bash
# Source after selecting an immutable retained multi-dimensional baseline attempt.
_MULTIDIM_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AAR_REPO="$(cd -- "${_MULTIDIM_DIR}/.." && pwd)"
export AAR_REPO REPO="${AAR_REPO}"
if [ -n "${AAR_EXPECTED_COMMIT:-}" ]; then
  unset AAR_EXPECTED_BRANCH
else
  export AAR_EXPECTED_BRANCH="${AAR_EXPECTED_BRANCH:-uv}"
fi
# An attempt-local source snapshot intentionally has no virtual environment.
# Preserve the operator-selected shared runtime when one was exported and use
# the source-adjacent environment only for ordinary branch worktrees.
export HARNESS_PY="${HARNESS_PY:-${AAR_REPO}/.venv/bin/python}"
export PYTHONPATH="${AAR_REPO}${PYTHONPATH:+:${PYTHONPATH}}"
export AAR_BENCHMARK_DOCS="${AAR_REPO}/benchmark_docs"
export BENCHMARK_DOCS_DIR="${AAR_REPO}/benchmark_docs"

export AXIS=honesty_sycophancy_concealing_uncertainty
export MODEL=gemma4_31b
export TARGET_MODEL_PATH=/checkpoint/ram/shared/models/google/gemma-4-31B-it
export AAR_SUITE_BENCHMARKS="mask_factual mask_continuation mask_disinformation sycophancy_eval llm_uncertainty_bench verbalized_ece abstentionbench deceptionbench_reward sycon_fp sciq_uncertainty mmlu gsm8k ifeval"
export AAR_TARGET_ENABLE_THINKING=1

export JUDGE_BACKEND=model_api
export JUDGE_MODEL=gpt-5-6-luna
export MASK_JUDGE_MODEL=gpt-5-6-luna
export OAI_API=
export OPENAI_API_KEY=
export AAR_MONITOR_BACKEND=model_api
export MONITOR_MODEL=claude-4-8-opus
export AAR_AGENT_MODEL=claude-opus-4-8
export AAR_EFFORT=max
export LITREVIEW_MODEL=claude-sonnet-4-6
export LITREVIEW_MIN=36

export EVAL_RUN_BATCH=2
export EVAL_BATCH_SIZE=2
export EVAL_AUTO_CEILING=8192
export EVAL_RUN_GEN_CEILING=8192
export EVAL_REQUIRE_EXACT_MAX_NEW_TOKENS=1
export EVAL_RUN_GEN_CEILING_BENCHMARKS="mask_factual mask_continuation mask_disinformation sycophancy_eval verbalized_ece abstentionbench deceptionbench_reward sycon_fp gsm8k ifeval"
export EVAL_FAIL_ON_ALLOCATOR_WARNING=1
export EVAL_MAX_TRUNCATION_RATE=0.10
export EVAL_TRUNCATION_MIN_COMPLETIONS=20
export TORCH_DISABLE_NATIVE_JIT=1

export AAR_REQUIRE_ADAPTER=1
# Keep only the submitted adapter needed for evaluation/champion selection.
# Smoke launchers may explicitly opt into retaining the redundant staging copy.
export AAR_KEEP_CHECKPOINTS="${AAR_KEEP_CHECKPOINTS:-0}"
export AAR_METHOD_TRAIN_MINUTES=30
export AAR_SLURM_ACCOUNT=ram
export AAR_SLURM_PARTITION=g3
export AAR_AGENT_QOS=g3_ram_high
export AAR_TRAIN_QOS=g3_ram_high
export AAR_EVAL_QOS=g3_ram_high
export AAR_TRAIN_GPUS=1
export AAR_EVAL_GPUS=2
export AAR_EVAL_GPU_CAP=2
export AAR_MAX_CONCURRENT_TRAIN_JOBS=2
# The research agent already polls the persisted job id and score path. Release
# the training GPU as soon as the checkpoint is staged instead of holding it
# idle throughout the substantially longer 13-leg evaluation.
export AAR_TRAIN_EXIT_AFTER_SUBMIT=1
export META_CLAUDE_CODE_RELEASE=2.1.278
export AAR_WEB_MODE=meta_secure
export LITREVIEW_WEB_MODE=meta_secure
export AAR_START_EVAL_WORKER=1
export AAR_HIDE_EVAL_CONFIG=1
export AAR_DIMENSIONS=honesty,sycophancy,concealing_uncertainty
export LITREVIEW_DIMENSIONS=honesty,sycophancy,concealing_uncertainty
export LITREVIEW_TARGET_MODEL=google/gemma-4-31B-it
# Confirmed 2026-10-01: Appendix E-style coverage weighting with the stricter
# per-optimized-benchmark regression gate documented in the experiment README.
export AAR_MULTIDIM_SCORING_CONFIRMED=1

export AAR_RUNTIME_BASE="/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-v0"
export AAR_RUNTIME_ROOT="${AAR_RUNTIME_ROOT:-${AAR_RUNTIME_BASE}}"
export AAR_BASELINE_OVERRIDES="${AAR_RUNTIME_ROOT}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${AAR_RUNTIME_ROOT}/eval/holdout/gemma4_31b"
export LITREVIEW_CACHE_ROOT="${LITREVIEW_CACHE_ROOT:-${AAR_REPO}/_runs/litreview}"
export LIT_AXIS_DIR="${LIT_AXIS_DIR:-${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty}"
export AAR_TEAM_ID="${AAR_TEAM_ID:-honesty-sycophancy-concealing-gemma4_31b-opus48-v0}"
export AAR_SERVE_V2_DEPLOYMENT_DIR=/checkpoint/ram/shared/vllm_deployments_v2/winnieyangwn-gemma-4-31B-it
export AAR_SERVE_V2_MODEL=gemma-4-31B-it

unset _MULTIDIM_DIR
