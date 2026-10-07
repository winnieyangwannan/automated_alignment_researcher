#!/bin/bash
# Add single-node evaluator workers to an active storage-backed Run 7 attempt.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
ATTEMPT_DIR="$(realpath -e -- "${1:?usage: $0 <storage-attempt-dir> [worker-count]}")"
WORKERS="${2:-2}"
SECRET_ENV="${AAR_RUN7_SECRET_ENV:-/storage/home/winnieyangwn/aar-worktrees/uv/.env}"
SECRET_ENV="$(realpath -e -- "${SECRET_ENV}")"

case "${WORKERS}" in
  ''|*[!0-9]*) echo "replacement worker count must be an integer" >&2; exit 2;;
esac
if [ "${WORKERS}" -lt 1 ] || [ "${WORKERS}" -gt 5 ]; then
  echo "replacement worker count must be between 1 and 5" >&2
  exit 2
fi
[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "Run 7 evaluator replacement requires branch multi_vllm" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "Run 7 evaluator replacement requires a clean tracked worktree" >&2
  exit 2
fi
[ -f "${ATTEMPT_DIR}/metadata/children.env" ] || {
  echo "not a launched storage-backed Run 7 attempt: ${ATTEMPT_DIR}" >&2
  exit 2
}

mapfile -t team_dirs < <(find "${ATTEMPT_DIR}/aar_teams" -mindepth 1 -maxdepth 1 \
  -type d -name '*-run7-storage-continuation-*' -print)
[ "${#team_dirs[@]}" -eq 1 ] || {
  echo "expected exactly one storage-continuation team directory" >&2
  exit 2
}
export TEAM_DIR="${team_dirs[0]}"
AAR_TEAM_ID="$(basename -- "${TEAM_DIR}")"
export AAR_TEAM_ID
export AAR_REPO="${REPO}"
export AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"
export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"
export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/holdout/gemma4_31b"
export AAR_BASELINE_OVERRIDES="${ATTEMPT_DIR}/metadata/gemma4_31b_multidimensional_baseline.json"
export BASELINES_PATH="${ATTEMPT_DIR}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export SUBMISSIONS_DIR="${TEAM_DIR}/submissions"
export SCORES_DIR="${TEAM_DIR}/scores"
export AAR_EVAL_RUNTIME_ROOT="${TEAM_DIR}/_eval_private"
export HARNESS_ENV="${SECRET_ENV}"

source_root="${REPO}/data/LLM-Uncertainty-Bench"
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || {
  echo "attempt-local HF_HOME was overridden" >&2
  exit 2
}
export AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_FUNCTIONAL_SMOKE=1
export AAR_MULTIDIM_SCORING_CONFIRMED=1
export EVAL_INFERENCE_BACKEND=vllm
export EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536
export EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768
export EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1
export EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint
export EVAL_VLLM_REQUIRE_MERGED=1
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH=/checkpoint/ram/shared/vllm_deployments_v2/baseline_gemma-4-31b-ib/src/serve_api_v2/worker/worker_vllm.sh
export AAR_VLLM_WORKER_SHA256=913c3286e237ed2231c64de200a4bcfc65729292a05c6aa3a88100f8c0248361
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}"
export AAR_VLLM_EPHEMERAL_MERGED=1
export AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680
export AAR_EVAL_WORKERS="${WORKERS}"
export AAR_EVAL_GPUS=4
export AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00
export AAR_EVAL_IDLE_SECONDS=604200

for required in "${TARGET_MODEL_PATH}" \
  "${HOLDOUT_DIR}/${SUITE_NAME}/${SUITE_NAME}.yaml" \
  "${AAR_BASELINE_OVERRIDES}" "${AAR_VLLM_WORKER_SH}" \
  "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" \
  "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${HARNESS_ENV}" "${TEAM_DIR}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done
[ "$(sha256sum "${AAR_VLLM_WORKER_SH}" | awk '{print $1}')" = \
  "${AAR_VLLM_WORKER_SHA256}" ] || {
  echo "vLLM worker snapshot hash mismatch" >&2
  exit 2
}
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || {
    echo "required runtime credential is empty: ${secret_name}" >&2
    exit 2
  }
done

submission="$(bash "${REPO}/scripts/launch_eval_worker.sh" \
  honesty_sycophancy_concealing_uncertainty "${AAR_EVAL_IDLE_SECONDS}" \
  "${WORKERS}")"
printf '%s\n' "${submission}"
mapfile -t worker_ids < <(printf '%s\n' "${submission}" | \
  awk '/^\[launch\] evaluator [0-9]+\/[0-9]+ -> job [0-9]+$/{print $NF}')
[ "${#worker_ids[@]}" -eq "${WORKERS}" ] || {
  echo "expected ${WORKERS} replacement evaluator job IDs" >&2
  exit 1
}
[ "$(printf '%s\n' "${worker_ids[@]}" | sort -u | wc -l)" -eq "${WORKERS}" ] || {
  echo "replacement evaluator job IDs are not distinct" >&2
  exit 1
}

record="${ATTEMPT_DIR}/metadata/evaluator_replacement_$(date -u +%Y%m%dT%H%M%SZ).txt"
{
  printf 'recovery_kind=single_node_evaluator_replacement\n'
  printf 'reason=multi_node_allocation_invalid_for_local_gpu_replicas\n'
  printf 'replaced_jobs=1750344 1750347\n'
  printf 'evaluator_jobs=%s\n' "${worker_ids[*]}"
  printf 'evaluator_nodes_per_job=1\n'
  printf 'evaluator_gpus_per_job=4\n'
  printf 'git_commit=%s\n' "$(git -C "${REPO}" rev-parse HEAD)"
} | tee "${record}"
