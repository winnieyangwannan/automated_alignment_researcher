#!/bin/bash
#SBATCH --job-name=aar-run10-kimi-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through run_10/launch/submit_run_10.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing commit}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing baseline}"
RECOVERED_SOURCES="${AAR_RECOVERED_BASELINE_SOURCES:?missing sources}"
MODE="${AAR_RUN10_MODE:?missing canary/full mode}"
RESUME_SMOKE="${AAR_RUN10_RESUME_SMOKE:-0}"
CANARY_ITERATIONS="${AAR_RUN10_CANARY_ITERATIONS:-1}"
case "${RESUME_SMOKE}" in 0|1) ;; *) echo "invalid AAR_RUN10_RESUME_SMOKE" >&2; exit 2;; esac
[ "${RESUME_SMOKE}" = 0 ] || [ "${MODE}" = smoke ] || { echo "resume is smoke-only" >&2; exit 2; }
case "${CANARY_ITERATIONS}" in
  ''|*[!0-9]*) echo "canary iterations must be an integer" >&2; exit 2 ;;
esac
[ "${CANARY_ITERATIONS}" -ge 1 ] && [ "${CANARY_ITERATIONS}" -le 5 ] || {
  echo "canary iterations must be between 1 and 5" >&2
  exit 2
}
export HF_HOME="${ATTEMPT_DIR}/cache/huggingface"
# shellcheck disable=SC1091
source "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/config/configure_run_10_environment.sh"
team_id_prefix="${AAR_RUN10_TEAM_ID_PREFIX:-honesty-sycophancy-concealing-gemma4_31b-kimi26-run10}"
export AAR_TEAM_ID="${team_id_prefix}-${MODE}-${SLURM_JOB_ID}"
if [ "${MODE}" = smoke ]; then
  seeds="${AAR_RESEARCH_SEEDS:-smoke}"
  iterations="${AAR_MAX_ITERATIONS_PER_CHAIN:-1}"
  hours="${AAR_CHAIN_HOURS:-2}"
  lifecycle_eval_workers="${AAR_EVAL_WORKERS:-1}"
  lifecycle_eval_gpus="${AAR_EVAL_GPUS:-4}"
  lifecycle_eval_time="${AAR_EVAL_TIME:-01:00:00}"
  lifecycle_eval_idle_seconds="${AAR_EVAL_IDLE_SECONDS:-120}"
  lifecycle_eval_on_demand="${AAR_EVAL_ON_DEMAND:-1}"
  export AAR_START_EVAL_WORKER=0 AAR_EVAL_WORKERS=0
  export AAR_MAX_CONCURRENT_TRAIN_JOBS="${AAR_MAX_CONCURRENT_TRAIN_JOBS:-1}"
  export AAR_METHOD_SMOKE="${AAR_METHOD_SMOKE:-1}"
  export AAR_TRAIN_TIME="${AAR_TRAIN_TIME:-00:15:00}"
  # The lifecycle canary retains its training copy for adapter-reload proof.
  export AAR_KEEP_CHECKPOINTS=1
elif [ "${MODE}" = canary ]; then
  seeds=canary; iterations="${CANARY_ITERATIONS}"; hours=17
  export AAR_MAX_CONCURRENT_TRAIN_JOBS=1 AAR_EVAL_WORKERS=1 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
  export AAR_EVAL_TIME=18:00:00 AAR_EVAL_IDLE_SECONDS=61200
else
  seeds="alpha beta gamma delta epsilon"; iterations=50; hours=167
  export AAR_MAX_CONCURRENT_TRAIN_JOBS=5 AAR_EVAL_WORKERS=5 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
  export AAR_PRETRAIN_SMOKE=1
  export AAR_EVAL_TIME=7-00:00:00 AAR_EVAL_IDLE_SECONDS=604200
fi

[ "$(git -C "${REPO}" branch --show-current)" = "${AAR_EXPECTED_BRANCH}" ] || { echo "wrong branch" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit drift" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" "${TARGET_MODEL_PATH}" "${AAR_VLLM_WORKER_SH}" \
  "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${HARNESS_ENV}" "${KIMI_CLI_PATH}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done
[ "$(sha256sum "${AAR_VLLM_WORKER_SH}" | awk '{print $1}')" = "${AAR_VLLM_WORKER_SHA256}" ] || { echo "evaluator snapshot changed" >&2; exit 2; }
for secret_name in HF_TOKEN MODEL_API_KEY; do [ -n "${!secret_name:-}" ] || { echo "missing ${secret_name}" >&2; exit 2; }; done
"${HARNESS_PY}" "${REPO}/scripts/prepare_llm_uncertainty_source.py" --output-root "$(dirname -- "${LLM_UNCERTAINTY_SOURCE_MANIFEST}")" --verify-only >/dev/null

mkdir -p "${ATTEMPT_DIR}/metadata"
if [ "${RESUME_SMOKE}" = 0 ]; then
  "${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" "${REUSED_BASELINE}" \
    --recovered-source-dir "${RECOVERED_SOURCES}" --provenance-output "${ATTEMPT_DIR}/metadata/baseline_reuse_provenance.json" >/dev/null
  cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
else
  [ -f "${ATTEMPT_DIR}/metadata/baseline_reuse_provenance.json" ] || { echo "baseline provenance missing" >&2; exit 2; }
  [ -f "${AAR_BASELINE_OVERRIDES}" ] || { echo "attempt baseline copy missing" >&2; exit 2; }
fi
"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" "${AAR_BASELINE_OVERRIDES}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null
if [ "${MODE}" != smoke ]; then
  bash "${REPO}/scripts/publish_holdout.sh"
fi

expected=1
if [ "${MODE}" = smoke ]; then
  expected="$(wc -w <<< "${seeds}" | tr -d ' ')"
elif [ "${MODE}" = full ]; then
  expected=5
fi

if [ "${RESUME_SMOKE}" = 1 ]; then
  smoke_proof="${ATTEMPT_DIR}/metadata/method_smoke_passed.json"
  [ "$(jq -r '.status' "${smoke_proof}")" = passed ] || { echo "passed smoke proof missing" >&2; exit 2; }
  adapter_path="$(jq -r '.runs[0].adapter_path // .adapter_path' "${smoke_proof}")"
  original_team_dir="$(dirname -- "$(dirname -- "${adapter_path}")")"
  [ -d "${original_team_dir}" ] || { echo "original smoke team is missing" >&2; exit 2; }
  AAR_TEAM_ID="$(basename -- "${original_team_dir}")"
  export AAR_TEAM_ID
  mapfile -t chain_ids < <(jq -r '.research_chain_jobs[]? // empty' "${smoke_proof}")
  [ "${#chain_ids[@]}" -gt 0 ] || chain_ids=("$(jq -r '.research_chain_job' "${smoke_proof}")")
  evaluator_ids=()
  echo "[run10] resuming passed smoke for team ${AAR_TEAM_ID}; no research or training relaunch"
else
  launch_log="${ATTEMPT_DIR}/metadata/launch_run10_${MODE}.txt"
  bash "${REPO}/scripts/launch_team.sh" "${seeds}" "${iterations}" "${hours}" | tee "${launch_log}"
  mapfile -t evaluator_ids < <(awk '/^\[launch\] evaluator [0-9]+\/[0-9]+ -> job [0-9]+$/{print $NF}' "${launch_log}")
  mapfile -t chain_ids < <(awk '/^\[team\] chain [a-z]+ -> job [0-9]+$/{print $NF}' "${launch_log}")
  expected_evaluators="${expected}"; [ "${MODE}" = smoke ] && expected_evaluators=0
  if [ "${#evaluator_ids[@]}" -ne "${expected_evaluators}" ] || [ "${#chain_ids[@]}" -ne "${expected}" ]; then
    echo "missing child job IDs" >&2
    exit 1
  fi
  if [ "${expected_evaluators}" -gt 0 ]; then
    [ "$(printf '%s\n' "${evaluator_ids[@]}" | sort -u | wc -l)" -eq "${expected_evaluators}" ] || { echo "duplicate evaluator IDs" >&2; exit 1; }
  fi
  [ "$(printf '%s\n' "${chain_ids[@]}" | sort -u | wc -l)" -eq "${expected}" ] || { echo "duplicate chain IDs" >&2; exit 1; }
  {
    printf 'evaluator_jobs=%s\n' "${evaluator_ids[*]}"
    printf 'research_chain_jobs=%s\n' "${chain_ids[*]}"
    printf 'research_seeds=%s\n' "${seeds}"
    printf 'max_iterations_per_chain=%s\n' "${iterations}"
    printf 'evaluator_gpus_per_job=%s\nresearch_backend=kimi\nresearch_model=Kimi-K2.6\nephemeral_merged_checkpoints=1\n' "$([ "${MODE}" = smoke ] && echo 0 || echo 4)"
  } > "${ATTEMPT_DIR}/metadata/children.env"
  echo "[run10] ${MODE} launch verified with ${expected} chain(s) and ${expected_evaluators} evaluator(s)"
fi

if [ "${MODE}" = smoke ]; then
  if [ "${RESUME_SMOKE}" = 0 ]; then
    echo "[run10] waiting for the generated method's real-GPU one-step smoke"
    "${HARNESS_PY}" "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/canary/monitor_method_smoke.py" \
      "${ATTEMPT_DIR}" --expected-chains "${expected}" --timeout-seconds 6900 --poll-seconds 10
  fi
  smoke_proof="${ATTEMPT_DIR}/metadata/method_smoke_passed.json"
  mapfile -t run_ids < <(jq -r '.runs[]?.run_id // empty' "${smoke_proof}")
  mapfile -t adapter_paths < <(jq -r '.runs[]?.adapter_path // empty' "${smoke_proof}")
  if [ "${#run_ids[@]}" -eq 0 ]; then
    run_ids=("$(jq -r '.run_id' "${smoke_proof}")")
    adapter_paths=("$(jq -r '.adapter_path' "${smoke_proof}")")
  fi
  if [ "${#run_ids[@]}" -ne "${expected}" ] || [ "${#adapter_paths[@]}" -ne "${expected}" ]; then
    echo "method smoke proof does not contain ${expected} runs" >&2
    exit 1
  fi
  export TEAM_DIR="${ATTEMPT_DIR}/aar_teams/${AAR_TEAM_ID}"
  export SUBMISSIONS_DIR="${TEAM_DIR}/submissions" SCORES_DIR="${TEAM_DIR}/scores"

  [ "${lifecycle_eval_on_demand}" = 1 ] || {
    echo "[run10] lifecycle evaluation must be configured on demand" >&2
    exit 2
  }
  export AAR_SUITE_BENCHMARKS="${AAR_SUITE_BENCHMARKS:-verbalized_ece}"
  export AAR_PUBLISH_FORCE_N="${AAR_PUBLISH_FORCE_N:-2}"
  echo "[run10] method smoke passed; publishing ${AAR_PUBLISH_FORCE_N}-item lifecycle evaluation and staging the same adapter"
  export HOLDOUT_DIR="${ATTEMPT_DIR}/eval/lifecycle_holdout_v3/gemma4_31b"
  export BASELINES_PATH="${ATTEMPT_DIR}/eval/prompt_baselines_v3.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
  bash "${REPO}/scripts/publish_holdout.sh"
  lifecycle_suite="${HOLDOUT_DIR}/${SUITE_NAME}/${SUITE_NAME}.yaml"
  "${HARNESS_PY}" \
    "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/canary/verification/verify_evaluation_contract.py" \
    --suite "${lifecycle_suite}" \
    --benchmarks "${AAR_SUITE_BENCHMARKS}" \
    --items "${AAR_PUBLISH_FORCE_N}" \
    --output "${ATTEMPT_DIR}/metadata/lifecycle_evaluation_contract.json"
  for index in "${!run_ids[@]}"; do
    run_id="${run_ids[${index}]}"
    adapter_path="${adapter_paths[${index}]}"
    if [ -f "${SUBMISSIONS_DIR}/${run_id}/.submitted" ] && \
       [ -f "${SUBMISSIONS_DIR}/${run_id}/model/adapter_config.json" ]; then
      echo "[run10] reusing staged immutable adapter for ${run_id}"
    else
      "${HARNESS_PY}" -c \
        'import sys; from aar.transport import put_model; print(put_model(sys.argv[1], sys.argv[2]))' \
        "${adapter_path}" "${run_id}"
    fi
  done

  export AAR_EVAL_WORKERS="${lifecycle_eval_workers}"
  export AAR_EVAL_GPUS="${lifecycle_eval_gpus}" AAR_EVAL_GPU_CAP="${lifecycle_eval_gpus}"
  export AAR_EVAL_RETRY_FAILED=1
  export AAR_EVAL_TIME="${lifecycle_eval_time}" AAR_EVAL_IDLE_SECONDS="${lifecycle_eval_idle_seconds}"
  export EVAL_VLLM_MAX_NUM_SEQS=8 EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=8192
  eval_launch_log="${ATTEMPT_DIR}/metadata/launch_on_demand_evaluator.txt"
  "${REPO}/scripts/launch_eval_worker.sh" "${SUITE_NAME}" "${AAR_EVAL_IDLE_SECONDS}" "${AAR_EVAL_WORKERS}" | tee "${eval_launch_log}"
  mapfile -t evaluator_ids < <(awk '/^\[launch\] evaluator [0-9]+\/[0-9]+ -> job [0-9]+$/{print $NF}' "${eval_launch_log}")
  [ "${#evaluator_ids[@]}" -eq "${AAR_EVAL_WORKERS}" ] || { echo "on-demand evaluator IDs missing" >&2; exit 1; }
  [ "$(printf '%s\n' "${evaluator_ids[@]}" | sort -u | wc -l)" -eq "${AAR_EVAL_WORKERS}" ] || { echo "duplicate on-demand evaluator IDs" >&2; exit 1; }
  {
    printf 'evaluator_jobs=%s\n' "${evaluator_ids[*]}"
    printf 'research_chain_jobs=%s\n' "${chain_ids[*]}"
    printf 'research_seeds=%s\n' "${seeds}"
    printf 'max_iterations_per_chain=%s\n' "${iterations}"
    printf 'evaluator_gpus_per_job=%s\nresearch_backend=kimi\nresearch_model=Kimi-K2.6\nephemeral_merged_checkpoints=1\n' "${AAR_EVAL_GPUS}"
    printf 'method_smoke_passed=1\non_demand_evaluator=1\n'
  } > "${ATTEMPT_DIR}/metadata/children.env"
  echo "[run10] ${#evaluator_ids[@]} on-demand evaluator(s) launched for ${#run_ids[@]} smoked run(s)"
fi
