#!/bin/bash
# Shared Run 10 runtime configuration for initial launch and targeted recovery.
# Source only after setting REPO, ATTEMPT_DIR, MODE, and HARNESS_ENV.

set -euo pipefail
: "${REPO:?missing Run 10 repository}"
: "${ATTEMPT_DIR:?missing Run 10 attempt directory}"
: "${MODE:?missing Run 10 mode}"
case "${MODE}" in smoke|canary|full) ;; *)
  echo "invalid Run 10 mode: ${MODE}" >&2
  # shellcheck disable=SC2317  # direct-execution fallback after sourced return
  return 2 2>/dev/null || exit 2
  ;;
esac

export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"
export AAR_EXPECTED_BRANCH="${AAR_EXPECTED_BRANCH:-multi_kimi}" AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || {
  echo "attempt-local HF_HOME overridden" >&2
  # shellcheck disable=SC2317  # direct-execution fallback after sourced return
  return 2 2>/dev/null || exit 2
}
mkdir -p "${HF_HOME}"

export AAR_BASELINE_OVERRIDES="${ATTEMPT_DIR}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT_DIR}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT=/storage/home/winnieyangwn/aar-recovery/run7_continuation_shared/librarian
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"

export EVAL_INFERENCE_BACKEND=vllm EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536 EVAL_VLLM_MAX_NUM_SEQS=256 EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768
export EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90 EVAL_VLLM_ENABLE_PREFIX_CACHING=1 EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint EVAL_VLLM_REQUIRE_MERGED=1
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH="${ATTEMPT_DIR}/runtime/serve_api_v2/worker/worker_vllm.sh"
export AAR_VLLM_WORKER_SHA256=913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}" AAR_VLLM_EPHEMERAL_MERGED=1
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

export AAR_AGENT_BACKEND=kimi AAR_WEB_MODE=native_web
export KIMI_CLI_PATH="${AAR_RUN10_KIMI_ROOT:-/storage/home/${USER}/tools/kimi-code-2.1.1}/node_modules/.bin/kimi"
export PATH="${AAR_RUN10_NODE_ROOT:-/storage/home/${USER}/tools/node-v22.22.0-linux-arm64}/bin:${PATH}"
export AAR_KIMI_SERVE_DEPLOYMENT="${AAR_KIMI_SERVE_DEPLOYMENT:-steerability_8-kimi26}" AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT="/storage/home/${USER}/ram_common/vllm_tools/serve_api_v2"
export KIMI_MODEL_MAX_CONTEXT_SIZE=262144 KIMI_MODEL_MAX_OUTPUT_SIZE=65536
export KIMI_MODEL_MAX_COMPLETION_TOKENS=65536
export KIMI_MODEL_CAPABILITIES=tool_use KIMI_MODEL_REASONING_KEY=reasoning_content
export AAR_KIMI_MCP_MAX_TEXT_CHARS=16000 AAR_KIMI_SCORE_WAIT_SECONDS=21600
export AAR_REQUIRE_METHOD_CONTRACT=1 AAR_REQUIRE_GEMMA4_TARGETS=1 AAR_REQUIRE_METHOD_SMOKE=1
export AAR_WRITE_TRAIN_FAILURE_MARKER=1 AAR_TRAIN_MEM=128G AAR_REQUIRE_TRAIN_RECEIPT=1
unset KIMI_AGENT_MODEL

export AAR_GPT_JUDGE_SPEND_CAP_USD=500 OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=0 AAR_FUNCTIONAL_SMOKE=1
export AAR_MULTIDIM_SCORING_CONFIRMED=1 AAR_START_EVAL_WORKER=1
