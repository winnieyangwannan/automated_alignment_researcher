#!/bin/bash
# Replace only Run 7's evaluator pool after a shared runtime-snapshot failure.
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_eval_recovery.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing retained Run 7 attempt}"
EXPECTED_COMMIT="${AAR_EXPECTED_COMMIT:?missing submitted commit}"
export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

export AAR_EXPECTED_BRANCH=multi_vllm
export AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"
export AAR_BASELINE_OVERRIDES="${ATTEMPT_DIR}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT_DIR}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export TEAM_DIR="${ATTEMPT_DIR}/aar_teams/honesty-sycophancy-concealing-gemma4_31b-opus48-fiveagent-vllm-run7-v0"
export SUBMISSIONS_DIR="${TEAM_DIR}/submissions"
export SCORES_DIR="${TEAM_DIR}/scores"
export AAR_EVAL_RUNTIME_ROOT="${TEAM_DIR}/_eval_private"
export AAR_TEAM_ID=honesty-sycophancy-concealing-gemma4_31b-opus48-fiveagent-vllm-run7-v0
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
export AAR_VLLM_MERGED_ROOT="${ATTEMPT_DIR}/merged_candidates"
export AAR_EVAL_WORKERS=5
export AAR_EVAL_GPUS=4
export AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00
export AAR_EVAL_IDLE_SECONDS=604200

[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || {
  echo "attempt-local HF_HOME was overridden" >&2
  exit 2
}
[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "wrong HPC branch" >&2
  exit 2
}
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || {
  echo "HPC commit drift" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked HPC worktree is dirty" >&2
  exit 2
fi
for required in "${TARGET_MODEL_PATH}" "${HOLDOUT_DIR}/${SUITE_NAME}/${SUITE_NAME}.yaml" \
  "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" \
  "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${HARNESS_ENV}" "${TEAM_DIR}"; do
  [ -e "${required}" ] || {
    echo "required evaluator-recovery artifact missing: ${required}" >&2
    exit 2
  }
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
"${HARNESS_PY}" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "$(dirname -- "${LLM_UNCERTAINTY_SOURCE_MANIFEST}")" \
  --verify-only >/dev/null

recovery_log="${ATTEMPT_DIR}/metadata/eval_recovery_${SLURM_JOB_ID}.txt"
worker_submission="$(bash "${REPO}/scripts/launch_eval_worker.sh" \
  honesty_sycophancy_concealing_uncertainty "${AAR_EVAL_IDLE_SECONDS}" \
  "${AAR_EVAL_WORKERS}")"
printf '%s\n' "${worker_submission}" | tee "${recovery_log}"
mapfile -t worker_ids < <(printf '%s\n' "${worker_submission}" | \
  awk '/^\[launch\] evaluator [1-5]\/5 -> job [0-9]+$/{print $NF}')
[ "${#worker_ids[@]}" -eq 5 ] || {
  echo "expected five evaluator recovery job IDs" >&2
  exit 1
}
[ "$(printf '%s\n' "${worker_ids[@]}" | sort -u | wc -l)" -eq 5 ] || {
  echo "evaluator recovery job IDs are not distinct" >&2
  exit 1
}
{
  printf 'recovery_kind=evaluator_pool_replacement\n'
  printf 'worker_script=%s\n' "${AAR_VLLM_WORKER_SH}"
  printf 'worker_sha256=%s\n' "${AAR_VLLM_WORKER_SHA256}"
  printf 'evaluator_jobs=%s\n' "${worker_ids[*]}"
  printf 'evaluator_gpus_per_job=4\n'
} >> "${recovery_log}"
echo "[run7-recovery] submitted evaluator jobs ${worker_ids[*]}"
