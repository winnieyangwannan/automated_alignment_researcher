#!/bin/bash
#SBATCH --job-name=aar-gemma-vllm-run8-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_8.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing retained attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted commit}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing retained baseline}"
ATTEMPT_DIR="$(realpath -e -- "${ATTEMPT_DIR}")"
case "${ATTEMPT_DIR}" in
  "/storage/home/${USER:?}/aar-runs/"*) ;;
  *) echo "Run 8 attempt escaped /storage/home/${USER}/aar-runs: ${ATTEMPT_DIR}" >&2; exit 2 ;;
esac
export TMPDIR="${ATTEMPT_DIR}/tmp"
export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"
export AAR_EXPECTED_BRANCH=autodata

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

[ "${HF_HOME}" = "${ATTEMPT_DIR}/cache/huggingface" ] || {
  echo "run-local HF_HOME was overridden" >&2
  exit 2
}
mkdir -p "${HF_HOME}"
mkdir -p "${TMPDIR}"
echo "[run8] isolated HF_HOME=${HF_HOME}"

export AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"
export AAR_BASELINE_OVERRIDES="${ATTEMPT_DIR}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT_DIR}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT="/checkpoint/ram/aar/${USER}/honesty-sycophancy-gemma4-31b-v0/librarian"
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"
export AAR_LIT_AXIS_READ_ONLY=1

export EVAL_INFERENCE_BACKEND=vllm
export EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536
export EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768
export EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1
export EVAL_VLLM_ENFORCE_EAGER=0
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH="${AAR_RUN8_VLLM_WORKER_SH:?missing validated Gemma vLLM worker}"
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ATTEMPT_DIR}"
export AAR_VLLM_MERGED_ROOT="${ATTEMPT_DIR}/merged_candidates"

export AAR_TEAM_ID=honesty-sycophancy-concealing-gemma4_31b-opus48-autodata-run8-v0
export AAR_CLAUDE_SPEND_CAP_USD=200
export AAR_GPT_JUDGE_SPEND_CAP_USD=500
export AAR_CLAUDE_SESSION_BUDGET_USD=100
export OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1
export AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=1
export AAR_VERIFY_RUN8_AUTODATA=1
export AAR_FUNCTIONAL_SMOKE=1
export AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_MAX_CONCURRENT_TRAIN_JOBS=1
export AAR_EVAL_WORKERS=1
export AAR_EVAL_GPUS=4
export AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00
export AAR_EVAL_IDLE_SECONDS=604200
export AAR_START_EVAL_WORKER=1
# The operator pipeline/evaluator/services keep HARNESS_ENV and their secrets.
# The research Slurm job receives only scripts/aar_runtime_env.sh's positive
# allowlist, and its Claude SDK child gets a second sanitization boundary.
export AAR_CHAIN_SANITIZE_ENV=1
export AAR_RUNTIME_ENV_DISABLE_FILE=1
export AAR_RESEARCH_ENV_ISOLATION=1
# Convert the general operator credential into the monitor-only name before
# launch_team builds the research-chain Slurm allowlist.  The Claude SDK child
# boundary removes this purpose-specific value as well.
export AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY:?missing Model API monitor credential}"

# Production AutoData is mandatory. Every proposal gets a distinct run_id, but
# both iterations use this one service-side budget scope and cap.
export AAR_AUTODATA=1
export AAR_AUTODATA_REQUIRED=1
export AAR_AUTODATA_CONTRACT_SMOKE=0
export AAR_AUTODATA_SHA="${AAR_RUN8_AUTODATA_SHA:?missing AutoData framework pin}"
export AAR_AUTODATA_TOKEN_FILE="${AAR_RUN8_ADAPTER_TOKEN_FILE:?missing adapter token file}"
unset AAR_AUTODATA_TOKEN
export AAR_AUTODATA_RESOURCE_PROFILE="${AAR_RUN8_RESOURCE_PROFILE:?missing resource profile}"
export AAR_AUTODATA_RESOURCE_PROFILE_SHA256="${AAR_RUN8_RESOURCE_PROFILE_SHA256:?missing profile digest}"
export AAR_AUTODATA_BUDGET_SCOPE_ID="${AAR_RUN8_BUDGET_SCOPE_ID:?missing shared budget scope}"
export AAR_AUTODATA_MAX_COST_USD="${AAR_RUN8_AUTODATA_MAX_COST_USD:?missing shared budget cap}"
export AAR_AUTODATA_REQUIRED_RETAINED_ROWS="${AAR_RUN8_REQUIRED_RETAINED_ROWS:?missing retained-row target}"
export AAR_AUTODATA_TRAINING_VIEW=sft
export AAR_AUTODATA_HTTP_TIMEOUT=120

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "wrong branch" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit drift" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked HPC worktree is dirty" >&2
  exit 2
fi
for required in "${REUSED_BASELINE}" "${TARGET_MODEL_PATH}" "${LIT_AXIS_DIR}/manifest.json" \
  "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" \
  "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${HARNESS_ENV}" \
  "${AAR_RUN8_EXECSIDECAR_TOKEN_FILE}" "${AAR_AUTODATA_TOKEN_FILE}" \
  "${AAR_RUN8_BROKER_TOKEN_FILE}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || {
    echo "required runtime credential is empty: ${secret_name}" >&2
    exit 2
  }
done
"${HARNESS_PY}" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "$(dirname -- "${LLM_UNCERTAINTY_SOURCE_MANIFEST}")" \
  --verify-only >/dev/null
[ "${EVAL_INFERENCE_BACKEND}" = vllm ] || { echo "vLLM backend not enabled" >&2; exit 2; }
[ "${AAR_VLLM_CONTAINER_IMAGE}" = docker.io/vllm/vllm-openai:v0.25.1 ] || {
  echo "unvalidated image" >&2
  exit 2
}
if [ "${AAR_EVAL_WORKERS}" != 1 ] || [ "${AAR_EVAL_GPUS}" != 4 ]; then
  echo "run 8 requires one four-GPU evaluator job" >&2
  exit 2
fi

mkdir -p "${ATTEMPT_DIR}/metadata"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" \
  --provenance-output "${ATTEMPT_DIR}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${AAR_BASELINE_OVERRIDES}" >/dev/null
bash "${REPO}/scripts/publish_holdout.sh"

services_job_id=""
launch_complete=0
cleanup_failed_launch() {
  status=$?
  if [ "${launch_complete}" != 1 ] && [ -n "${services_job_id}" ]; then
    scancel "${services_job_id}" 2>/dev/null || true
  fi
  exit "${status}"
}
trap cleanup_failed_launch EXIT

services_job_id="$(sbatch --parsable \
  --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=16 --mem=64G --time=7-00:00:00 \
  --job-name=aar-run8-autodata-services \
  --output="${ATTEMPT_DIR}/logs/autodata-services-%j.out" \
  --export=AAR_REPO="${REPO}",AAR_RUN_ATTEMPT_DIR="${ATTEMPT_DIR}",AAR_BASELINE_GIT_COMMIT="${EXPECTED_COMMIT}",HARNESS_ENV="${HARNESS_ENV}",AUTODATA_SOURCE_ROOT="${AUTODATA_SOURCE_ROOT}",AAR_RUN8_AUTODATA_SHA="${AAR_RUN8_AUTODATA_SHA}",AAR_RUN8_BROKER_PYTHON="${AAR_RUN8_BROKER_PYTHON}",AAR_RUN8_EXECSIDECAR_TOKEN_FILE="${AAR_RUN8_EXECSIDECAR_TOKEN_FILE}",AAR_RUN8_ADAPTER_TOKEN_FILE="${AAR_RUN8_ADAPTER_TOKEN_FILE}",AAR_RUN8_BROKER_TOKEN_FILE="${AAR_RUN8_BROKER_TOKEN_FILE}",AAR_RUN8_GENERATOR_URL="${AAR_RUN8_GENERATOR_URL}",AAR_RUN8_BUDGET_SCOPE_ID="${AAR_RUN8_BUDGET_SCOPE_ID}",AAR_RUN8_RESOURCE_PROFILE="${AAR_RUN8_RESOURCE_PROFILE}",AAR_RUN8_RESOURCE_PROFILE_SHA256="${AAR_RUN8_RESOURCE_PROFILE_SHA256}",AAR_RUN8_AUTODATA_MAX_COST_USD="${AAR_RUN8_AUTODATA_MAX_COST_USD}",AAR_RUN8_REQUIRED_RETAINED_ROWS="${AAR_RUN8_REQUIRED_RETAINED_ROWS}",AAR_RUN8_AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD="${AAR_RUN8_AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD}",AAR_RUN8_GENERATOR_INPUT_USD_PER_MILLION="${AAR_RUN8_GENERATOR_INPUT_USD_PER_MILLION}",AAR_RUN8_GENERATOR_OUTPUT_USD_PER_MILLION="${AAR_RUN8_GENERATOR_OUTPUT_USD_PER_MILLION}",AAR_RUN8_JUDGE_INPUT_USD_PER_MILLION="${AAR_RUN8_JUDGE_INPUT_USD_PER_MILLION}",AAR_RUN8_JUDGE_OUTPUT_USD_PER_MILLION="${AAR_RUN8_JUDGE_OUTPUT_USD_PER_MILLION}",AAR_RUN8_LAUNCH_JOB_ID="${SLURM_JOB_ID}",USER="${USER}" \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_8/run_8_autodata_services.sbatch")"
services_job_id="${services_job_id%%;*}"

services_env="${ATTEMPT_DIR}/metadata/autodata_services.env"
for _ in $(seq 1 600); do
  [ -s "${services_env}" ] && break
  service_state="$(squeue -h -j "${services_job_id}" -o '%T' | head -n 1)"
  [ -n "${service_state}" ] || {
    echo "AutoData services job ended before publishing readiness" >&2
    exit 1
  }
  sleep 2
done
[ -s "${services_env}" ] || { echo "timed out waiting for AutoData services" >&2; exit 1; }
# shellcheck disable=SC1090
source "${services_env}"
[ "${AAR_RUN8_SERVICES_JOB_ID}" = "${services_job_id}" ] || {
  echo "AutoData services metadata has the wrong job id" >&2
  exit 2
}
export AAR_AUTODATA_URL
"${HARNESS_PY}" - "${AAR_AUTODATA_URL}/health" "${AAR_AUTODATA_TOKEN_FILE}" "${AAR_AUTODATA_SHA}" <<'PY'
import json, sys, urllib.request
token = open(sys.argv[2], encoding="utf-8").read().strip()
request = urllib.request.Request(sys.argv[1], headers={"Authorization": "Bearer " + token})
with urllib.request.urlopen(request, timeout=10) as response:
    value = json.load(response)
if value != {"status": "ok", "pipeline_sha": sys.argv[3]}:
    raise SystemExit("AutoData adapter health response does not match the pinned framework")
PY

export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint
export EVAL_VLLM_REQUIRE_MERGED=1
launch_log="${ATTEMPT_DIR}/metadata/launch_run8_vllm_submission.txt"
bash "${REPO}/scripts/launch_team.sh" "alpha" 2 167 | tee "${launch_log}"

mapfile -t evaluator_ids < <(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${launch_log}")
mapfile -t chain_ids < <(awk '/^\[team\] chain alpha -> job [0-9]+$/{print $NF}' "${launch_log}")
[ "${#evaluator_ids[@]}" -eq 1 ] || { echo "expected one evaluator job ID" >&2; exit 1; }
[ "${#chain_ids[@]}" -eq 1 ] || { echo "expected one research-chain job ID" >&2; exit 1; }
if [ "${services_job_id}" = "${evaluator_ids[0]}" ] || \
   [ "${services_job_id}" = "${chain_ids[0]}" ] || \
   [ "${evaluator_ids[0]}" = "${chain_ids[0]}" ]; then
  echo "Run 8 child job IDs are not distinct" >&2
  exit 1
fi

children_tmp="$(mktemp "${ATTEMPT_DIR}/metadata/.children.env.XXXXXX")"
{
  printf 'autodata_services_job=%s\n' "${services_job_id}"
  printf 'evaluator_job=%s\n' "${evaluator_ids[0]}"
  printf 'research_chain_job=%s\n' "${chain_ids[0]}"
  printf 'research_seed=alpha\n'
  printf 'max_iterations_per_chain=2\n'
  printf 'evaluator_gpus_per_job=4\n'
  printf 'autodata_budget_scope_id=%s\n' "${AAR_AUTODATA_BUDGET_SCOPE_ID}"
} > "${children_tmp}"
mv -- "${children_tmp}" "${ATTEMPT_DIR}/metadata/children.env"
launch_complete=1
trap - EXIT
echo "[run8] launch verified: live AutoData services, one sequential two-iteration chain, and one four-GPU evaluator"
