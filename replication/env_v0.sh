#!/bin/bash
# Source this file from the replication worktree on fair-cw-use2-1.
_REPLICATION_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AAR_REPO="$(cd -- "${_REPLICATION_DIR}/.." && pwd)"
export AAR_REPO
REPO="${AAR_REPO}"
export REPO
export AAR_EXPECTED_BRANCH=winnie-replication-v0
export HARNESS_PY="${AAR_REPO}/.venv/bin/python"
export PYTHONPATH="${AAR_REPO}${PYTHONPATH:+:${PYTHONPATH}}"
export AAR_BENCHMARK_DOCS="${AAR_REPO}/benchmark_docs"
export BENCHMARK_DOCS_DIR="${AAR_REPO}/benchmark_docs"

export AXIS=sycophancy
export MODEL=gemma4_31b
export TARGET_MODEL_PATH=/checkpoint/ram/shared/models/google/gemma-4-31B-it
export AAR_SUITE_BENCHMARKS="sycophancy_eval sycon_fp mmlu gsm8k ifeval"
export AAR_TARGET_ENABLE_THINKING=1
# Torch 2.14's optional native Triton kernels JIT-compile a helper against
# Python.h, which is absent from the managed compute image. Use stock CUDA
# kernels; the GPU smoke records the resulting warm throughput.
export TORCH_DISABLE_NATIVE_JIT=1
export AAR_REQUIRE_ADAPTER=1
export AAR_KEEP_CHECKPOINTS=1
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
export AAR_WEB_MODE=meta_secure
export LITREVIEW_WEB_MODE=meta_secure
export AAR_FUNCTIONAL_SMOKE=1
export AAR_START_EVAL_WORKER=1
export AAR_HIDE_EVAL_CONFIG=1

export AAR_RUNTIME_ROOT="/checkpoint/ram/aar/${USER:?}/sycophancy-gemma4-31b-single-v0"
export AAR_BASELINE_OVERRIDES="${AAR_RUNTIME_ROOT}/metadata/gemma4_31b_baseline.json"
export HOLDOUT_DIR="${AAR_RUNTIME_ROOT}/eval/holdout/gemma4_31b"
export AAR_TEAM_ID=sycophancy-gemma4_31b-opus48-v0
export AAR_SERVE_V2_DEPLOYMENT_DIR=/checkpoint/ram/shared/vllm_deployments_v2/winnieyangwn-gemma-4-31B-it
export AAR_SERVE_V2_MODEL=gemma-4-31B-it

unset _REPLICATION_DIR
