#!/bin/bash
# Resume selected teams in a stopped Run 14 full attempt without resetting it.
set -euo pipefail
umask 077

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <run14-full-attempt> [\"seed ...\"]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN14_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO="$(cd -- "${RUN14_DIR}/../../.." && pwd)"
ATTEMPT="$(realpath -e -- "$1")"
REQUESTED_SEEDS="${2:-alpha beta gamma delta epsilon}"
CANONICAL_CONFIG="$(realpath -e -- "${RUN14_DIR}/config/run.yaml")"
RETAINED_CONFIG="$(realpath -e -- "${ATTEMPT}/metadata/run.yaml")"
SECRET_ENV="$(realpath -e -- "${AAR_RUN14_SECRET_ENV:-${REPO}/.env}")"

case "${ATTEMPT}" in
  /checkpoint/ram/aar/"${USER:?}"/run14_native_generation/full_attempts/*) ;;
  *) echo "not a Run 14 full attempt: ${ATTEMPT}" >&2; exit 2;;
esac
[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 14 recovery requires branch autodata" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi

submission="${ATTEMPT}/metadata/submission.txt"
full_launch="${ATTEMPT}/metadata/full-launch.env"
children="${ATTEMPT}/metadata/children.tsv"
for required in "${submission}" "${full_launch}" "${children}" \
  "${ATTEMPT}/metadata/one_chain_lifecycle_passed.json" \
  "${ATTEMPT}/metadata/five_chain_lifecycle_passed.json"; do
  [ -f "${required}" ] || { echo "missing retained attempt metadata: ${required}" >&2; exit 2; }
done
[ "$(sed -n 's/^attempt_dir=//p' "${submission}")" = "${ATTEMPT}" ] || {
  echo "submission record is not bound to this attempt" >&2
  exit 2
}
[ "$(sed -n 's/^mode=//p' "${submission}")" = full ] || {
  echo "Run 14 recovery only supports full attempts" >&2
  exit 2
}
original_commit="$(sed -n 's/^git_commit=//p' "${submission}")"
[[ "${original_commit}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "submission record has no full source commit" >&2
  exit 2
}
git -C "${REPO}" merge-base --is-ancestor "${original_commit}" HEAD || {
  echo "current recovery source does not descend from ${original_commit}" >&2
  exit 2
}
retained_config_sha256="$(sha256sum -- "${RETAINED_CONFIG}" | awk '{print $1}')"
original_config_sha256="$(
  git -C "${REPO}" show \
    "${original_commit}:experiments/dishonest_sycophancy_concealing/run_14/config/run.yaml" \
    | sha256sum | awk '{print $1}'
)"
[ "${retained_config_sha256}" = "${original_config_sha256}" ] || {
  echo "attempt-retained config does not match its recorded source commit" >&2
  exit 2
}
normalized_recovery_config_sha256="$(
  sed \
    -e '/^  # Emit vLLM scheduler throughput, request, prefix-cache, and KV-cache stats\.$/d' \
    -e '/^  vllm_log_stats: true$/d' \
    "${CANONICAL_CONFIG}" | sha256sum | awk '{print $1}'
)"
if [ "$(grep -c '^  vllm_log_stats: true$' "${CANONICAL_CONFIG}")" != 1 ] || \
   [ "${normalized_recovery_config_sha256}" != "${retained_config_sha256}" ]; then
  echo "recovery config differs from the attempt by more than vllm_log_stats=true" >&2
  exit 2
fi

launch_job="$(sed -n 's/^launch_job_id=//p' "${submission}")"
[[ "${launch_job}" =~ ^[0-9]+$ ]] || { echo "invalid retained launch job" >&2; exit 2; }
[ "$(sed -n 's/^data_generation_backend=//p' "${full_launch}")" = native ] || {
  echo "attempt did not retain native data generation" >&2
  exit 2
}
[ "$(sed -n 's/^autodata=//p' "${full_launch}")" = 0 ] || {
  echo "attempt did not retain AutoData disabled" >&2
  exit 2
}
[ "$(sed -n 's/^chains=//p' "${full_launch}")" = 5 ] || {
  echo "attempt is not the five-chain topology" >&2
  exit 2
}
[ "$(sed -n 's/^target_score_result_pairs=//p' "${full_launch}")" = 50 ] || {
  echo "attempt target is not 50 pairs per chain" >&2
  exit 2
}
[ "$(sed -n 's/^seeds=//p' "${full_launch}")" = "alpha beta gamma delta epsilon" ] || {
  echo "attempt has an unexpected seed topology" >&2
  exit 2
}
[ "$(wc -l < "${children}" | tr -d ' ')" = 5 ] || {
  echo "attempt does not retain five child rows" >&2
  exit 2
}

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
export AAR_RUN_CONFIG="${CANONICAL_CONFIG}" AAR_RUN_ATTEMPT_DIR="${ATTEMPT}"
export AAR_RUNTIME_ROOT="${ATTEMPT}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
eval "$("${HARNESS_PY}" "${REPO}/scripts/load_aar_run_config.py" "${CANONICAL_CONFIG}")"

[ "${AAR_AUTODATA:?missing data-generation backend}" = 0 ] || {
  echo "Run 14 recovery requires data_generation.backend=native" >&2
  exit 2
}
[ "${AAR_AGENT_BACKEND:?missing agent backend}" = kimi ] || {
  echo "Run 14 recovery requires Kimi" >&2
  exit 2
}
[ "${AAR_RESEARCH_SEEDS:?}" = "alpha beta gamma delta epsilon" ] || exit 2
[ "${AAR_TARGET_SUCCESSFUL_ITERATIONS:?}" = 50 ] || exit 2
[ "${AAR_MAX_ITERATIONS_PER_CHAIN:?}" = 60 ] || exit 2
[ "${AAR_EVAL_WORKERS:?}" = 1 ] || exit 2
[ "${AAR_EVAL_GPUS:?}" = 4 ] || exit 2
[ "${AAR_EVAL_ON_DEMAND:?}" = 0 ] || exit 2
[ "${EVAL_VLLM_LOG_STATS:?missing vLLM telemetry policy}" = 1 ] || {
  echo "Run 14 recovery requires evaluation.vllm_log_stats=true" >&2
  exit 2
}
while IFS= read -r name; do unset "${name}"; done < <(compgen -A variable AAR_AUTODATA_)
export AAR_AUTODATA=0

for secret_name in HF_TOKEN MODEL_API_KEY; do
  [ -n "${!secret_name:-}" ] || { echo "Run 14 recovery requires ${secret_name}" >&2; exit 2; }
done
export AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY}"
export HF_HOME="${ATTEMPT}/cache/huggingface"
expected_hf_home="$(realpath -m -- "${ATTEMPT}/cache/huggingface")"
[ "$(realpath -m -- "${HF_HOME}")" = "${expected_hf_home}" ] || exit 2

recovery_bundle="$(realpath -e -- "${AAR_RUN14_RECOVERY_BUNDLE:-/storage/home/${USER}/aar-recovery/run7_20261007T004406Z-1b3303d02821/baseline_salvage}")"
reused_baseline="${recovery_bundle}/gemma4_31b_multidimensional_baseline.json"
recovered_sources="${recovery_bundle}/source_artifacts"
source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${HARNESS_PY}" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${source_root}" --verify-only >/dev/null
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${reused_baseline}" --recovered-source-dir "${recovered_sources}" >/dev/null

export AAR_BASELINE_OVERRIDES="${ATTEMPT}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT=/storage/home/winnieyangwn/aar-recovery/run7_continuation_shared/librarian
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"
export LITREVIEW_SKIP=1 AAR_LIT_AXIS_READ_ONLY=1
for required in "${AAR_BASELINE_OVERRIDES}" "${HOLDOUT_DIR}/${SUITE_NAME}/${SUITE_NAME}.yaml" \
  "${TARGET_MODEL_PATH}" "${LLM_UNCERTAINTY_SOURCE_MANIFEST}"; do
  [ -e "${required}" ] || { echo "missing recovery artifact: ${required}" >&2; exit 2; }
done

export EVAL_INFERENCE_BACKEND=vllm EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536 EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768 EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1 EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint EVAL_VLLM_REQUIRE_MERGED=1
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH="${ATTEMPT}/runtime/serve_api_v2/worker/worker_vllm.sh"
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT}" AAR_VLLM_EPHEMERAL_MERGED=1
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

export AAR_WEB_MODE=native_web
export KIMI_CLI_PATH=/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi
export PATH=/storage/home/${USER}/tools/node-v22.22.0-linux-arm64/bin:"${PATH}"
export AAR_KIMI_SERVE_DEPLOYMENT=steerability_8-kimi26 AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT=/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2
export KIMI_MODEL_MAX_CONTEXT_SIZE=262144 KIMI_MODEL_MAX_OUTPUT_SIZE=65536
export KIMI_MODEL_MAX_COMPLETION_TOKENS=65536 KIMI_MODEL_CAPABILITIES=tool_use
export KIMI_MODEL_REASONING_KEY=reasoning_content AAR_KIMI_MCP_MAX_TEXT_CHARS=65536
export AAR_KIMI_SCORE_WAIT_SECONDS=21600
unset KIMI_AGENT_MODEL

export AAR_REQUIRE_METHOD_CONTRACT=1 AAR_REQUIRE_GEMMA4_TARGETS=1 AAR_REQUIRE_METHOD_SMOKE=1
export AAR_WRITE_TRAIN_FAILURE_MARKER=1 AAR_TRAIN_MEM=128G AAR_REQUIRE_TRAIN_RECEIPT=1
export AAR_NO_LOCAL_GPU=true
export AAR_PRETRAIN_SMOKE=1 AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1
export OVERLOADED_MAX_RETRIES=0 AAR_FUNCTIONAL_SMOKE=1 AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_EVAL_GPU_CAP="${AAR_EVAL_GPUS}"
export AAR_START_EVAL_WORKER=1
export AAR_CHAIN_SANITIZE_ENV=1 AAR_RUNTIME_ENV_DISABLE_FILE=1
export AAR_RESEARCH_ENV_ISOLATION=0 AAR_HIDE_EVAL_CONFIG=1

for executable in "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" "${KIMI_CLI_PATH}"; do
  [ -x "${executable}" ] || { echo "missing recovery executable: ${executable}" >&2; exit 2; }
done

export AAR_RESUME_EXPECTED_BRANCH=autodata AAR_RESUME_EXPECTED_MODE=full
export AAR_RESUME_ALLOWED_SEEDS="alpha beta gamma delta epsilon"
export AAR_RESUME_DEFAULT_SEEDS="alpha beta gamma delta epsilon"
export AAR_RESUME_TEAM_PREFIX="run14-gemma4-31b-kimi26-"
export AAR_RESUME_TEAM_SUFFIX="-${launch_job}"
export AAR_RESUME_MAX_SESSIONS=60
export AAR_RESUME_HOURS="${AAR_RUN14_RESUME_HOURS:-167}"
export AAR_RESUME_JOB_PREFIX="aar-${SUITE_NAME}-gemma4_31b-run14"
export AAR_RESUME_RETRY_INTERRUPTED_TRAINING=1
AAR_RESUME_CONFIG_SHA256="$(sha256sum -- "${CANONICAL_CONFIG}" | awk '{print $1}')"
export AAR_RESUME_CONFIG_SHA256
# Optional one-shot audit guard, e.g.:
# alpha=58 beta=59 gamma=57 delta=58 epsilon=57
export AAR_RESUME_EXPECTED_REMAINING="${AAR_RUN14_EXPECTED_REMAINING:-}"

exec "${REPO}/scripts/resume_aar_multiteam.sh" "${ATTEMPT}" "${REQUESTED_SEEDS}"
