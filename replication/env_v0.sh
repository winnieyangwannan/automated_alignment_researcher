#!/bin/bash
# Source this file from the replication worktree on fair-cw-use2-1.
_REPLICATION_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AAR_REPO="$(cd -- "${_REPLICATION_DIR}/.." && pwd)"
export AAR_REPO
REPO="${AAR_REPO}"
export REPO
export AAR_EXPECTED_BRANCH=uv
export HARNESS_PY="${AAR_REPO}/.venv/bin/python"
export PYTHONPATH="${AAR_REPO}${PYTHONPATH:+:${PYTHONPATH}}"
export AAR_BENCHMARK_DOCS="${AAR_REPO}/benchmark_docs"
export BENCHMARK_DOCS_DIR="${AAR_REPO}/benchmark_docs"

export AXIS=sycophancy
export MODEL=gemma4_31b
export TARGET_MODEL_PATH=/checkpoint/ram/shared/models/google/gemma-4-31B-it
export AAR_SUITE_BENCHMARKS="sycophancy_eval sycon_fp mmlu gsm8k ifeval"
export AAR_TARGET_ENABLE_THINKING=1
# Replication-v0 judge parity: both the baseline and every candidate use the
# same canonical GPT-5.6 Luna route through FAIR Model API. Keep public OpenAI
# credentials explicitly empty so a caller's shell or the local .env cannot
# silently change the endpoint.
export JUDGE_BACKEND=model_api
export JUDGE_MODEL=gpt-5-6-luna
export OAI_API=
export OPENAI_API_KEY=

# Gemma-4-31B health-checked decoding. These run overrides are applied after the
# benchmark-doc defaults, so they remain identical for the baseline and all
# candidate evaluations. The 8192 ceiling bounds thinking plus final-answer
# generation for every generative benchmark in this replication suite.
# A run with allocator warnings, CUDA OOM, or more than 5% no-stop truncations
# (once at least 20 completions were generated) fails before any score is accepted.
export EVAL_RUN_BATCH=2
export EVAL_AUTO_CEILING=8192
export EVAL_RUN_GEN_CEILING=8192
export EVAL_RUN_NGRAM=4
export MASK_GENERATION_TOKEN_BUDGET=8192
# Apply the ceiling to every generative benchmark in this five-benchmark suite.
# MMLU is continuation-logprob scored and does not generate output tokens.
export EVAL_RUN_GEN_CEILING_BENCHMARKS="sycophancy_eval sycon_fp gsm8k ifeval"
export EVAL_FAIL_ON_ALLOCATOR_WARNING=1
export EVAL_MAX_TRUNCATION_RATE=0.05
export EVAL_TRUNCATION_MIN_COMPLETIONS=20
# Torch 2.14's optional native Triton kernels JIT-compile a helper against
# Python.h, which is absent from the managed compute image. Use stock CUDA
# kernels; the GPU smoke records the resulting warm throughput.
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

export AAR_AGENT_MODEL=claude-opus-4-8
export AAR_EFFORT=max
# Pin the newest already-cached ARM64 Claude binary. The launcher's moving
# "latest" target currently fails its host-side Manifold TLS prefetch.
export META_CLAUDE_CODE_RELEASE=2.1.278
export AAR_WEB_MODE=meta_secure
export LITREVIEW_WEB_MODE=meta_secure
export AAR_FUNCTIONAL_SMOKE=1
export AAR_START_EVAL_WORKER=1
export AAR_HIDE_EVAL_CONFIG=1

export AAR_RUNTIME_BASE="/checkpoint/ram/aar/${USER:?}/sycophancy-gemma4-31b-single-v0"
# A selected retained attempt may be supplied by a launcher (or by sourcing
# that attempt's attempt.env). The default remains the original v0 root.
export AAR_RUNTIME_ROOT="${AAR_RUNTIME_ROOT:-${AAR_RUNTIME_BASE}}"
export AAR_BASELINE_OVERRIDES="${AAR_RUNTIME_ROOT}/metadata/gemma4_31b_baseline.json"
export HOLDOUT_DIR="${AAR_RUNTIME_ROOT}/eval/holdout/gemma4_31b"
export AAR_TEAM_ID=sycophancy-gemma4_31b-opus48-v0
export AAR_SERVE_V2_DEPLOYMENT_DIR=/checkpoint/ram/shared/vllm_deployments_v2/winnieyangwn-gemma-4-31B-it
export AAR_SERVE_V2_MODEL=gemma-4-31B-it

unset _REPLICATION_DIR
