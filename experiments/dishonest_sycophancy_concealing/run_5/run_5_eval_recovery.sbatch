#!/bin/bash
#SBATCH --job-name=aar-run5-eval-recovery-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_eval_recovery.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing fresh recovery attempt}"
EXPECTED_COMMIT="${AAR_EXPECTED_COMMIT:?missing submitted commit}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing retained baseline}"
SOURCE_TEAM_DIR="${AAR_SOURCE_TEAM_DIR:?missing retained Run 5 team}"
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
export TEAM_DIR="${ATTEMPT_DIR}/aar_teams/run5-eval-recovery"
export SUBMISSIONS_DIR="${TEAM_DIR}/submissions"
export SCORES_DIR="${TEAM_DIR}/scores"
export AAR_EVAL_RUNTIME_ROOT="${TEAM_DIR}/_eval_private"
export LITREVIEW_CACHE_ROOT="/checkpoint/ram/aar/${USER}/honesty-sycophancy-gemma4-31b-v0/librarian"
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"

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
export AAR_VLLM_WORKER_SH=/checkpoint/ram/shared/vllm_deployments_v2/aar-gemma-4-31b-it/src/serve_api_v2/worker/worker_vllm.sh
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}"
export AAR_VLLM_MERGED_ROOT="${ATTEMPT_DIR}/merged_candidates"
export AAR_EVAL_GPUS=4
export AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=12:00:00

[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || {
  echo "attempt-local HF_HOME was overridden" >&2
  exit 2
}
[ "${EVAL_RUN_GEN_CEILING}" = 8192 ] || {
  echo "generation ceiling must be 8192" >&2
  exit 2
}
[ "${EVAL_REQUIRE_EXACT_MAX_NEW_TOKENS}" = 1 ] || {
  echo "exact per-request generation-budget contract must be enabled" >&2
  exit 2
}
[ "${EVAL_MAX_TRUNCATION_RATE}" = 0.10 ] || {
  echo "candidate truncation gate must be 0.10" >&2
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
if ! git -C "${REPO}" diff --quiet || \
   ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked HPC worktree is dirty" >&2
  exit 2
fi
for required in "${REUSED_BASELINE}" "${TARGET_MODEL_PATH}" "${LIT_AXIS_DIR}/manifest.json" \
  "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" \
  "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${HARNESS_ENV}"; do
  [ -e "${required}" ] || {
    echo "required recovery artifact missing: ${required}" >&2
    exit 2
  }
done
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || {
    echo "required runtime credential is empty: ${secret_name}" >&2
    exit 2
  }
done

for benchmark in verbalized_ece abstentionbench; do
  resolved="$("${HARNESS_PY}" -c \
    'import sys; from aar.benchmarks.base import run_generation_max_new_tokens; print(run_generation_max_new_tokens(sys.argv[1], int(sys.argv[2])))' \
    "${benchmark}" "$([ "${benchmark}" = verbalized_ece ] && echo 96 || echo 256)")"
  [ "${resolved}" = 8192 ] || {
    echo "${benchmark} did not resolve to an exact 8192-token request" >&2
    exit 2
  }
done
"${HARNESS_PY}" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "$(dirname -- "${LLM_UNCERTAINTY_SOURCE_MANIFEST}")" \
  --verify-only >/dev/null

mkdir -p "${HF_HOME}" "${TEAM_DIR}/logs" "${SUBMISSIONS_DIR}" "${SCORES_DIR}" \
  "${ATTEMPT_DIR}/metadata"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" \
  --provenance-output "${ATTEMPT_DIR}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
bash "${REPO}/scripts/publish_holdout.sh"

run_ids=(
  gemma4_31b-explore-pilot-1791275184-gemma4_31b_explore_pilot__faithful_self_report-1791277755779
  gemma4_31b-explore-pilot-1791275184-gemma4_31b_explore_pilot__native_faithful_report-1791283077478
)
for run_id in "${run_ids[@]}"; do
  source_model="${SOURCE_TEAM_DIR}/submissions/${run_id}/model"
  [ -s "${source_model}/adapter_model.safetensors" ] || {
    echo "retained adapter missing for ${run_id}" >&2
    exit 2
  }
  mkdir "${SUBMISSIONS_DIR}/${run_id}"
  ln -s "${source_model}" "${SUBMISSIONS_DIR}/${run_id}/model"
  printf 'source_run_id=%s\nsource_model=%s\n' "${run_id}" "${source_model}" \
    > "${SUBMISSIONS_DIR}/${run_id}/recovery_provenance.txt"
  touch "${SUBMISSIONS_DIR}/${run_id}/.submitted"
done

printf 'recovery_kind=evaluation_only\niterations=1,2\ngeneration_ceiling=8192\nmax_truncation_rate=0.10\nsource_team_dir=%s\n' \
  "${SOURCE_TEAM_DIR}" > "${ATTEMPT_DIR}/metadata/recovery_contract.txt"
worker_submission="$(bash "${REPO}/scripts/launch_eval_worker.sh" \
  honesty_sycophancy_concealing_uncertainty 600)"
printf '%s\n' "${worker_submission}" | tee \
  "${ATTEMPT_DIR}/metadata/eval_worker_submission.txt"
worker_job_id="$(printf '%s\n' "${worker_submission}" | awk '/Submitted batch job/{print $4}' | tail -1)"
[ -n "${worker_job_id}" ] || {
  echo "could not parse evaluator job id" >&2
  exit 2
}
printf 'eval_worker_job_id=%s\n' "${worker_job_id}" >> \
  "${ATTEMPT_DIR}/metadata/recovery_contract.txt"
echo "[run5-recovery] evaluation-only worker ${worker_job_id} submitted for iterations 1 and 2"
