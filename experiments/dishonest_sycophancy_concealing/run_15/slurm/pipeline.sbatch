#!/bin/bash
#SBATCH --job-name=aar-run15-native-launch
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=02:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through run_15/launch/submit_full.sh}"
ATTEMPT="${AAR_RUN_ATTEMPT_DIR:?missing attempt}"
RUN_CONFIG="${AAR_RUN_CONFIG:?missing run config}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing source commit}"
SOURCE_SNAPSHOT="${AAR_SOURCE_SNAPSHOT:?missing immutable source snapshot}"
LIFECYCLE_PROOF_POLICY="${AAR_RUN15_LIFECYCLE_PROOF_POLICY:-required}"
REUSED_BASELINE="${AAR_REUSED_BASELINE:?missing baseline}"
RECOVERED_SOURCES="${AAR_RECOVERED_BASELINE_SOURCES:?missing source bundle}"
export HF_HOME="${ATTEMPT}/cache/huggingface"

[ "${REPO}" = "${SOURCE_SNAPSHOT}" ] || { echo "source snapshot path drift" >&2; exit 2; }
[ "${REPO}" = "${ATTEMPT}/runtime/aar-source" ] || { echo "source is not attempt-local" >&2; exit 2; }
[ -z "$(git -C "${REPO}" branch --show-current)" ] || { echo "source snapshot is not detached" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "commit drift" >&2; exit 2; }
[ -z "$(git -C "${REPO}" remote)" ] || { echo "source snapshot retains a remote" >&2; exit 2; }
[ ! -e "${REPO}/.git/objects/info/alternates" ] || { echo "source snapshot has shared-object alternates" >&2; exit 2; }
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all)" ]; then
  echo "dirty source snapshot" >&2
  exit 2
fi
case "${RUN_CONFIG}" in
  "${REPO}"/*) ;;
  *) echo "Run 15 config is not source-pinned" >&2; exit 2 ;;
esac
case "${LIFECYCLE_PROOF_POLICY}" in
  required) ;;
  user_authorized_bypass)
    [ -s "${ATTEMPT}/metadata/lifecycle_proof_override.json" ] || {
      echo "user-authorized lifecycle-proof override metadata is missing" >&2
      exit 2
    }
    jq -e --arg git_commit "${EXPECTED_COMMIT}" \
      '.schema == "aar.run15-lifecycle-proof-override/v1" and
       .status == "user_authorized" and
       .scope == "full-five-chain-5x50" and
       .git_commit == $git_commit and
       .researcher_deployment == "autodata2_8-kimi26"' \
      "${ATTEMPT}/metadata/lifecycle_proof_override.json" >/dev/null || {
        echo "user-authorized lifecycle-proof override metadata is invalid" >&2
        exit 2
      }
    ;;
  *) echo "invalid Run 15 lifecycle-proof policy" >&2; exit 2 ;;
esac

# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
eval "$("${HARNESS_PY}" "${REPO}/scripts/load_aar_run_config.py" "${RUN_CONFIG}")"
[ "${AAR_AUTODATA:?missing data-generation backend}" = 0 ] || {
  echo "Run 15 requires native data generation" >&2
  exit 2
}
while IFS= read -r name; do unset "${name}"; done < <(compgen -A variable AAR_AUTODATA_)
export AAR_AUTODATA=0

mkdir -p "${HF_HOME}" "${ATTEMPT}/metadata"

unset AAR_EXPECTED_BRANCH
export AAR_EXPECTED_COMMIT="${EXPECTED_COMMIT}" AAR_RUNTIME_ROOT="${ATTEMPT}"
export AAR_BASELINE_OVERRIDES="${ATTEMPT}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ATTEMPT}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ATTEMPT}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT=/storage/home/winnieyangwn/aar-recovery/run7_continuation_shared/librarian
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"
export LITREVIEW_SKIP=1 AAR_LIT_AXIS_READ_ONLY=1

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
export AAR_KIMI_SERVE_DEPLOYMENT=autodata2_8-kimi26 AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT=/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2
export KIMI_MODEL_MAX_CONTEXT_SIZE=262144 KIMI_MODEL_MAX_OUTPUT_SIZE=65536
export KIMI_MODEL_MAX_COMPLETION_TOKENS=65536 KIMI_MODEL_CAPABILITIES=tool_use
export KIMI_MODEL_REASONING_KEY=reasoning_content AAR_KIMI_MCP_MAX_TEXT_CHARS=65536
export AAR_KIMI_SCORE_WAIT_SECONDS=21600
unset KIMI_AGENT_MODEL

export AAR_REQUIRE_METHOD_CONTRACT=1 AAR_REQUIRE_GEMMA4_TARGETS=1 AAR_REQUIRE_METHOD_SMOKE=1
export AAR_WRITE_TRAIN_FAILURE_MARKER=1 AAR_TRAIN_MEM=128G AAR_REQUIRE_TRAIN_RECEIPT=1
export AAR_PRETRAIN_SMOKE=1
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1
export OVERLOADED_MAX_RETRIES=0 AAR_FUNCTIONAL_SMOKE=1 AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_EVAL_GPU_CAP="${AAR_EVAL_GPUS:?}"
if [ "${AAR_EVAL_ON_DEMAND:-0}" = 1 ]; then
  export AAR_START_EVAL_WORKER=0
else
  export AAR_START_EVAL_WORKER=1
fi
export AAR_CHAIN_SANITIZE_ENV=1 AAR_RUNTIME_ENV_DISABLE_FILE=1
export AAR_HIDE_EVAL_CONFIG=1

[ "${AAR_AGENT_BACKEND:?}" = kimi ] || { echo "Run 15 requires Kimi" >&2; exit 2; }
[ "${AAR_FORUM_SCOPE:?missing forum scope}" = shared ] || {
  echo "Run 15 requires the paper-aligned shared forum" >&2
  exit 2
}
export AAR_SHARED_FORUM_DIR="${ATTEMPT}/forum"
mkdir -p "${AAR_SHARED_FORUM_DIR}"
if [ "${AAR_RUN15_MODE:?}" = full ]; then
  [ "${AAR_KIMI_CONTINUATION_EXHAUSTION_RETRYABLE:?}" = 1 ] || {
    echo "full five-chain Run 15 requires retryable continuation exhaustion" >&2
    exit 2
  }
fi
[ "${AAR_TARGET_SUCCESSFUL_ITERATIONS:?}" -ge 1 ] || { echo "invalid target pair count" >&2; exit 2; }
[ "${AAR_MAX_ITERATIONS_PER_CHAIN:?}" -ge "${AAR_TARGET_SUCCESSFUL_ITERATIONS}" ] || {
  echo "session budget is below the score/result-pair target" >&2; exit 2;
}
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" "${TARGET_MODEL_PATH}" \
  "${AAR_VLLM_WORKER_SH}" "${AAR_VLLM_MERGE_PY}" "${HARNESS_PY}" \
  "${LLM_UNCERTAINTY_SOURCE_MANIFEST}" "${KIMI_CLI_PATH}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done

"${HARNESS_PY}" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" \
  --provenance-output "${ATTEMPT}/metadata/baseline_reuse_provenance.json" >/dev/null
cp -- "${REUSED_BASELINE}" "${AAR_BASELINE_OVERRIDES}"
bash "${REPO}/scripts/publish_holdout.sh"

read -r -a seeds <<< "${AAR_RESEARCH_SEEDS:?missing research seeds}"
if [ "${AAR_EVAL_ON_DEMAND:-0}" = 1 ]; then
  [ "${#seeds[@]}" -eq 1 ] || [ "${#seeds[@]}" -eq 5 ] || {
    echo "on-demand lifecycle evaluation requires one or five chains" >&2
    exit 2
  }
  [ "${AAR_METHOD_SMOKE:-0}" = 1 ] || {
    echo "on-demand lifecycle evaluation requires one-step training mode" >&2
    exit 2
  }
  if [ "${#seeds[@]}" -eq 5 ]; then
    [ "${AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT:-0}" = 1 ] || {
      echo "five-chain lifecycle requires a one-chain prerequisite" >&2
      exit 2
    }
    [ -f "${ATTEMPT}/metadata/prerequisite_lifecycle_passed.json" ] || {
      echo "five-chain lifecycle prerequisite proof was not retained" >&2
      exit 2
    }
  fi
  lifecycle_suite="${HOLDOUT_DIR}/${SUITE_NAME}/${SUITE_NAME}.yaml"
  "${HARNESS_PY}" \
    "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/canary/verification/verify_evaluation_contract.py" \
    --suite "${lifecycle_suite}" \
    --benchmarks "${AAR_SUITE_BENCHMARKS:?missing lifecycle benchmarks}" \
    --items "${AAR_PUBLISH_FORCE_N:?missing lifecycle item count}" \
    --output "${ATTEMPT}/metadata/lifecycle_evaluation_contract.json"
fi
children="${ATTEMPT}/metadata/children.tsv"
: > "${children}"
chain_ids=()
evaluator_ids=()
if [ "${AAR_EVAL_ON_DEMAND:-0}" = 1 ]; then
  # A topology canary is one isolated team with a shared training queue and five
  # parallel research chains. The unchanged one-worker evaluator drains the
  # five adapters only after every real-GPU smoke proof passes.
  export AAR_TEAM_ID="run15-gemma4-31b-kimi26-lifecycle-${SLURM_JOB_ID}"
  launch_log="${ATTEMPT}/metadata/launch-lifecycle.txt"
  bash "${REPO}/scripts/launch_team.sh" "${AAR_RESEARCH_SEEDS}" \
    "${AAR_MAX_ITERATIONS_PER_CHAIN}" "${AAR_CHAIN_HOURS}" | tee "${launch_log}"
  mapfile -t chain_ids < <(
    awk '/^\[team\] chain [A-Za-z0-9._-]+ -> job [0-9]+$/{print $NF}' "${launch_log}"
  )
  [ "${#chain_ids[@]}" -eq "${#seeds[@]}" ] || {
    echo "missing lifecycle research-chain job IDs" >&2; exit 1;
  }
  for index in "${!seeds[@]}"; do
    printf '%s\t-\t%s\n' "${seeds[${index}]}" "${chain_ids[${index}]}" \
      | tee -a "${children}"
  done
else
  for seed in "${seeds[@]}"; do
    export AAR_TEAM_ID="run15-gemma4-31b-kimi26-${seed}-${SLURM_JOB_ID}"
    launch_log="${ATTEMPT}/metadata/launch-${seed}.txt"
    bash "${REPO}/scripts/launch_team.sh" "${seed}" \
      "${AAR_MAX_ITERATIONS_PER_CHAIN}" "${AAR_CHAIN_HOURS}" | tee "${launch_log}"
    chain="$(awk -v seed="${seed}" '$0 ~ "^\\[team\\] chain " seed " -> job [0-9]+$"{print $NF}' "${launch_log}")"
    if [ -z "${chain}" ]; then
      echo "missing research-chain job for ${seed}" >&2
      exit 1
    fi
    chain_ids+=("${chain}")
    evaluator="$(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${launch_log}")"
    [ -n "${evaluator}" ] || { echo "missing evaluator job for ${seed}" >&2; exit 1; }
    evaluator_ids+=("${evaluator}")
    printf '%s\t%s\t%s\n' "${seed}" "${evaluator}" "${chain}" | tee -a "${children}"
  done
fi

[ "$(wc -l < "${children}")" -eq "${#seeds[@]}" ] || { echo "incomplete child manifest" >&2; exit 1; }
[ "$(cut -f3 "${children}" | sort -u | wc -l)" -eq "${#seeds[@]}" ] || { echo "duplicate chain IDs" >&2; exit 1; }
if [ "${AAR_EVAL_ON_DEMAND:-0}" = 1 ]; then
  {
    printf 'evaluator_jobs=\n'
    printf 'research_chain_jobs=%s\n' "${chain_ids[*]}"
    printf 'research_seeds=%s\n' "${AAR_RESEARCH_SEEDS}"
    printf 'max_iterations_per_chain=%s\n' "${AAR_MAX_ITERATIONS_PER_CHAIN}"
  } > "${ATTEMPT}/metadata/children.env"
  echo "[run15] waiting for the generated method's real-GPU one-step smoke"
  "${HARNESS_PY}" \
    "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/canary/monitor_method_smoke.py" \
    "${ATTEMPT}" --expected-chains "${#seeds[@]}" --timeout-seconds 6900 --poll-seconds 10
  smoke_proof="${ATTEMPT}/metadata/method_smoke_passed.json"
  mapfile -t run_ids < <(jq -r '.runs[]?.run_id // empty' "${smoke_proof}")
  mapfile -t adapter_paths < <(jq -r '.runs[]?.adapter_path // empty' "${smoke_proof}")
  if [ "${#run_ids[@]}" -eq 0 ]; then
    run_ids=("$(jq -r '.run_id' "${smoke_proof}")")
    adapter_paths=("$(jq -r '.adapter_path' "${smoke_proof}")")
  fi
  if [ "${#run_ids[@]}" -ne "${#seeds[@]}" ] || \
     [ "${#adapter_paths[@]}" -ne "${#seeds[@]}" ]; then
    echo "method smoke proof does not contain ${#seeds[@]} runs" >&2
    exit 1
  fi
  export TEAM_DIR="${ATTEMPT}/aar_teams/${AAR_TEAM_ID}"
  export SUBMISSIONS_DIR="${TEAM_DIR}/submissions" SCORES_DIR="${TEAM_DIR}/scores"
  for index in "${!run_ids[@]}"; do
    "${HARNESS_PY}" -c \
      'import sys; from aar.transport import put_model; print(put_model(sys.argv[1], sys.argv[2]))' \
      "${adapter_paths[${index}]}" "${run_ids[${index}]}"
  done
  export AAR_EVAL_RETRY_FAILED=1
  export EVAL_VLLM_MAX_NUM_SEQS=8 EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=8192
  eval_launch_log="${ATTEMPT}/metadata/launch-on-demand-evaluator.txt"
  "${REPO}/scripts/launch_eval_worker.sh" "${SUITE_NAME}" \
    "${AAR_EVAL_IDLE_SECONDS}" "${AAR_EVAL_WORKERS}" | tee "${eval_launch_log}"
  mapfile -t evaluator_ids < <(
    awk '/^\[launch\] evaluator [0-9]+\/[0-9]+ -> job [0-9]+$/{print $NF}' "${eval_launch_log}"
  )
  [ "${#evaluator_ids[@]}" -eq "${AAR_EVAL_WORKERS}" ] || {
    echo "on-demand evaluator job IDs are missing" >&2; exit 1;
  }
  : > "${children}"
  for index in "${!seeds[@]}"; do
    printf '%s\t%s\t%s\n' "${seeds[${index}]}" "${evaluator_ids[0]}" \
      "${chain_ids[${index}]}" >> "${children}"
  done
  {
    printf 'evaluator_jobs=%s\n' "${evaluator_ids[*]}"
    printf 'expected_evaluator_jobs=%s\n' "${AAR_EVAL_WORKERS}"
    printf 'research_chain_jobs=%s\n' "${chain_ids[*]}"
    printf 'research_seeds=%s\n' "${AAR_RESEARCH_SEEDS}"
    printf 'max_iterations_per_chain=%s\n' "${AAR_MAX_ITERATIONS_PER_CHAIN}"
    printf 'evaluator_gpus_per_job=%s\n' "${AAR_EVAL_GPUS}"
    printf 'method_smoke_passed=1\non_demand_evaluator=1\n'
  } > "${ATTEMPT}/metadata/children.env"
else
  [ "$(cut -f2 "${children}" | sort -u | wc -l)" -eq "${#seeds[@]}" ] || {
    echo "duplicate evaluator IDs" >&2
    exit 1
  }
fi
printf 'research_backend=kimi\nresearch_model=Kimi-K2.6\nresearcher_deployment=autodata2_8-kimi26\ndata_generation_backend=native\nautodata=0\nforum_scope=%s\nforum_dir=%s\nlifecycle_proof_policy=%s\nchains=%s\ntarget_score_result_pairs=%s\nseeds=%s\n' \
  "${AAR_FORUM_SCOPE}" "${AAR_SHARED_FORUM_DIR}" \
  "${LIFECYCLE_PROOF_POLICY}" "${#seeds[@]}" "${AAR_TARGET_SUCCESSFUL_ITERATIONS}" "${AAR_RESEARCH_SEEDS}" \
  > "${ATTEMPT}/metadata/full-launch.env"
if [ "${AAR_RUN15_MODE}" = full ] && [ "${AAR_CONTROLLER_RECOVERY_ENABLED:-0}" = 1 ]; then
  [ "${AAR_RESUME_REUSE_EVALUATOR:?missing evaluator recovery policy}" = 1 ] || {
    echo "Run 15 automatic recovery requires evaluator reuse" >&2
    exit 2
  }
  export AAR_RUN15_SECRET_ENV="${HARNESS_ENV:?missing secret environment path}"
  export PYTHONPATH="${REPO}${PYTHONPATH:+:${PYTHONPATH}}"
  supervisor_job="$(sbatch --parsable --requeue \
    --account="${AAR_SLURM_ACCOUNT}" --partition="${AAR_SLURM_PARTITION}" \
    --qos="${AAR_AGENT_QOS}" --cpus-per-task=1 --mem=2G \
    --time="${AAR_CONTROLLER_SUPERVISOR_TIME:?missing supervisor time limit}" \
    --job-name="aar-run15-controller-supervisor" \
    --output="${ATTEMPT}/logs/controller-supervisor-%j.out" --export=ALL \
    "${REPO}/scripts/supervise_aar_multiteam.py" \
    --attempt "${ATTEMPT}" \
    --resume-script "${REPO}/experiments/dishonest_sycophancy_concealing/run_15/recovery/resume_full.sh" \
    --seeds "${seeds[@]}" \
    --target-pairs "${AAR_TARGET_SUCCESSFUL_ITERATIONS}" \
    --session-ceiling "${AAR_MAX_ITERATIONS_PER_CHAIN}" \
    --max-restarts "${AAR_CONTROLLER_MAX_RESTARTS:?missing controller restart limit}" \
    --max-plan-failures "${AAR_CONTROLLER_MAX_PLAN_FAILURES:?missing recovery-plan limit}" \
    --poll-seconds "${AAR_CONTROLLER_POLL_SECONDS:?missing controller poll interval}" \
    --backoff-seconds "${AAR_CONTROLLER_BACKOFF_SECONDS:?missing controller backoff}" \
    --unknown-state-timeout-seconds "${AAR_CONTROLLER_UNKNOWN_TIMEOUT_SECONDS:?missing scheduler-state timeout}")"
  supervisor_job="${supervisor_job%%;*}"
  [[ "${supervisor_job}" =~ ^[0-9]+$ ]] || {
    echo "invalid controller-supervisor job id: ${supervisor_job}" >&2
    exit 2
  }
  printf 'supervisor_job_id=%s\n' "${supervisor_job}" \
    | tee "${ATTEMPT}/metadata/controller-supervisor.env" \
    >> "${ATTEMPT}/metadata/full-launch.env"
  echo "[run15] controller supervisor -> job ${supervisor_job}"
fi
echo "[run15] launched ${#seeds[@]} native-generation chains with one shared forum"
