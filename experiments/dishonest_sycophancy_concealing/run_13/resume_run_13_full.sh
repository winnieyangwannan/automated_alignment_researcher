#!/bin/bash
# Resume the five-chain Run 13 attempt after relocating durable artifacts.
set -euo pipefail
umask 077

usage() {
  echo "usage: $0 <control-attempt-dir> <checkpoint-artifact-dir> [seeds]" >&2
  exit 2
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  usage
fi
CONTROL_ROOT="$(realpath -e -- "$1")"
ARTIFACT_ROOT="$(realpath -e -- "$2")"
REQUESTED_SEEDS="${3:-alpha beta gamma delta epsilon}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER:?}/autodata-pipelines-run13-main}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
SECRET_ENV="$(realpath -e -- "${AAR_RUN13_SECRET_ENV:-${REPO}/.env}")"
SV="/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2"
REQUIRED_AUTODATA_SHA=34f0a22c89a2a40e605afd43f3a7b11c25003ab7
GENERATOR_DEPLOYMENT=aar_8-kimi26

[ "${CONTROL_ROOT}" != "${ARTIFACT_ROOT}" ] || {
  echo "control and artifact roots must be distinct" >&2
  exit 2
}
case "${ARTIFACT_ROOT}" in
  /checkpoint/ram/${USER}/aar-runs/run13-full/*) ;;
  *) echo "artifact root must be below /checkpoint/ram/${USER}/aar-runs/run13-full" >&2; exit 2 ;;
esac
[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 13 recovery requires branch autodata" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
[ -x "${BROKER_PYTHON}" ] || { echo "missing AutoData broker runtime" >&2; exit 2; }
[ -x "${SV}/serve.sh" ] || { echo "missing pinned serve_api_v2" >&2; exit 2; }
[ "$(git -C "${AUTODATA_CHECKOUT}" branch --show-current)" = main ] || {
  echo "AutoData checkout must be on branch main" >&2
  exit 2
}
[ "$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)" = "${REQUIRED_AUTODATA_SHA}" ] || {
  echo "wrong AutoData revision" >&2
  exit 2
}
if ! git -C "${AUTODATA_CHECKOUT}" diff --quiet || \
    ! git -C "${AUTODATA_CHECKOUT}" diff --cached --quiet; then
  echo "tracked AutoData worktree is dirty" >&2
  exit 2
fi

# Preserve legacy absolute paths embedded in the AutoData state database.  Only
# run outputs are linked; credentials and the pinned runtime remain in the small
# control directory on /storage/home.
while IFS= read -r -d '' source; do
  name="$(basename -- "${source}")"
  case "${name}" in secrets|runtime) continue;; esac
  target="${CONTROL_ROOT}/${name}"
  if [ -L "${target}" ]; then
    [ "$(realpath -e -- "${target}")" = "${source}" ] || {
      echo "wrong artifact link: ${target}" >&2
      exit 2
    }
  elif [ -e "${target}" ]; then
    echo "refusing to replace existing control-root path: ${target}" >&2
    exit 2
  else
    ln -s -- "${source}" "${target}"
  fi
done < <(find "${ARTIFACT_ROOT}" -mindepth 1 -maxdepth 1 -print0)

submission="${CONTROL_ROOT}/metadata/submission.txt"
children="${CONTROL_ROOT}/metadata/children.tsv"
if [ ! -f "${submission}" ] || [ ! -f "${children}" ]; then
  echo "attempt is missing Run 13 launch metadata" >&2
  exit 2
fi
[ "$(sed -n 's/^chains=//p' "${submission}")" = 5 ] || {
  echo "target is not a five-chain Run 13 attempt" >&2
  exit 2
}
[ "$(sed -n 's/^target_pairs_per_chain=//p' "${submission}")" = 5 ] || {
  echo "target pair contract is not five per chain" >&2
  exit 2
}
original_commit="$(sed -n 's/^git_commit=//p' "${submission}")"
git -C "${REPO}" merge-base --is-ancestor "${original_commit}" HEAD || {
  echo "recovery source does not descend from original commit ${original_commit}" >&2
  exit 2
}
original_checkpoint="$(realpath -e -- "$(sed -n 's/^checkpoint_root=//p' "${submission}")")"

registry="${CONTROL_ROOT}/metadata/checkpoint-resume-jobs.tsv"
lock="${CONTROL_ROOT}/metadata/checkpoint-resume.lock"
exec 9>"${lock}"
flock -n 9 || { echo "another Run 13 checkpoint recovery is active" >&2; exit 2; }
touch "${registry}"

valid_seed() {
  case "$1" in alpha|beta|gamma|delta|epsilon) return 0;; *) return 1;; esac
}

resolve_team() {
  local seed="$1" chain_job="$2" candidate matches=()
  for candidate in "${CONTROL_ROOT}"/aar_teams/run13-gemma4-31b-opus48-"${seed}"-*; do
    [ -d "${candidate}" ] || continue
    if compgen -G "${candidate}/logs/*_${chain_job}.out" >/dev/null; then
      matches+=("${candidate}")
    fi
  done
  [ "${#matches[@]}" -eq 1 ] || {
    echo "expected exactly one retained team for ${seed} chain job ${chain_job}" >&2
    return 1
  }
  printf '%s\n' "${matches[0]}"
}

active_job_records="$(
  for job in $(squeue -u "${USER}" --noheader -o '%i'); do
    scontrol show job -o "${job}" 2>/dev/null || true
  done
)"
declare -A FIRST_JOBS=()
declare -A TEAM_DIRS=()
for seed in ${REQUESTED_SEEDS}; do
  valid_seed "${seed}" || { echo "invalid Run 13 seed: ${seed}" >&2; exit 2; }
  chain_job="$(awk -v seed="${seed}" '$1 == seed {print $3}' "${children}")"
  [[ "${chain_job}" =~ ^[0-9]+$ ]] || { echo "missing original chain job for ${seed}" >&2; exit 2; }
  team="$(resolve_team "${seed}" "${chain_job}")"
  physical_team="${ARTIFACT_ROOT}/aar_teams/$(basename -- "${team}")"
  [ -d "${physical_team}" ] || { echo "missing checkpoint team ${physical_team}" >&2; exit 2; }
  if grep -Fq "${team}/" <<< "${active_job_records}" || \
      grep -Fq "${physical_team}/" <<< "${active_job_records}"; then
    echo "refusing duplicate active jobs for ${seed}" >&2
    exit 2
  fi
  FIRST_JOBS["${seed}"]="${chain_job}"
  TEAM_DIRS["${seed}"]="${team}"
done

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
for name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!name:-}" ] || { echo "missing ${name}" >&2; exit 2; }
done

export HF_HOME="${ARTIFACT_ROOT}/cache/huggingface"
export AAR_RUN_ATTEMPT_DIR="${CONTROL_ROOT}"
export AAR_RUNTIME_ROOT="${CONTROL_ROOT}"
export AAR_RUNTIME_ARTIFACT_ROOT="${ARTIFACT_ROOT}"
export AAR_RUN13_CHECKPOINT_ROOT="${original_checkpoint}"
export AAR_BASELINE_OVERRIDES="${ARTIFACT_ROOT}/metadata/gemma4_31b_multidimensional_baseline.json"
export HOLDOUT_DIR="${ARTIFACT_ROOT}/eval/holdout/gemma4_31b"
export BASELINES_PATH="${ARTIFACT_ROOT}/baselines.honesty_sycophancy_concealing_uncertainty.google_gemma-4-31B-it.json"
export LITREVIEW_CACHE_ROOT=/storage/home/winnieyangwn/aar-recovery/run7_continuation_shared/librarian
export LIT_AXIS_DIR="${LITREVIEW_CACHE_ROOT}/honesty_sycophancy_concealing_uncertainty"
export LITREVIEW_SKIP=1 AAR_LIT_AXIS_READ_ONLY=1

export EVAL_INFERENCE_BACKEND=vllm EVAL_FAIL_ON_SCORING_ERROR=1
export EVAL_VLLM_MAX_MODEL_LEN=65536 EVAL_VLLM_MAX_NUM_SEQS=256
export EVAL_VLLM_MAX_NUM_BATCHED_TOKENS=32768 EVAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export EVAL_VLLM_ENABLE_PREFIX_CACHING=1 EVAL_VLLM_ENFORCE_EAGER=0
export EVAL_VLLM_LORA_STRATEGY=merged_checkpoint EVAL_VLLM_REQUIRE_MERGED=1
export AAR_VLLM_CONTAINER_IMAGE=docker.io/vllm/vllm-openai:v0.25.1
export AAR_VLLM_WORKER_SH="${CONTROL_ROOT}/runtime/serve_api_v2/worker/worker_vllm.sh"
export AAR_VLLM_MERGE_PY=/storage/home/winnieyangwn/envs/steerability-client/bin/python
export AAR_VLLM_CONTAINER_RW_MOUNT="${ARTIFACT_ROOT}"
export AAR_VLLM_EPHEMERAL_MERGED=0 AAR_VLLM_EPHEMERAL_MIN_FREE_BYTES=75161927680

export AAR_AGENT_BACKEND=claude AAR_AGENT_MODEL=claude-opus-4-8
export AAR_WEB_MODE=meta_secure CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:-/usr/local/bin/claude}"
export KIMI_CLI_PATH=/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi
export PATH=/storage/home/${USER}/tools/node-v22.22.0-linux-arm64/bin:"${PATH}"
export AAR_KIMI_SERVE_DEPLOYMENT="${GENERATOR_DEPLOYMENT}" AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT="${SV}" KIMI_MODEL_CAPABILITIES=tool_use
export KIMI_MODEL_MAX_CONTEXT_SIZE=262144 KIMI_MODEL_MAX_OUTPUT_SIZE=65536
export KIMI_MODEL_MAX_COMPLETION_TOKENS=65536 KIMI_MODEL_REASONING_KEY=reasoning_content
export AAR_KIMI_MCP_MAX_TEXT_CHARS=16000 AAR_KIMI_SCORE_WAIT_SECONDS=21600
export AAR_CLAUDE_SPEND_CAP_USD=100 AAR_CLAUDE_SESSION_BUDGET_USD=100
export AAR_GPT_JUDGE_SPEND_CAP_USD=500
unset KIMI_AGENT_MODEL

export AAR_REQUIRE_METHOD_CONTRACT=1 AAR_REQUIRE_GEMMA4_TARGETS=1 AAR_REQUIRE_METHOD_SMOKE=1
export AAR_WRITE_TRAIN_FAILURE_MARKER=1 AAR_TRAIN_MEM=128G AAR_REQUIRE_TRAIN_RECEIPT=1
export AAR_KEEP_CHECKPOINTS=1 AAR_PRETRAIN_SMOKE=1 AAR_MAX_CONCURRENT_TRAIN_JOBS=1
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1 AAR_REQUIRE_PHASE_TIMINGS=1
export AAR_TARGET_SUCCESSFUL_ITERATIONS=1 OVERLOADED_MAX_RETRIES=0
export AAR_FUNCTIONAL_SMOKE=1 AAR_MULTIDIM_SCORING_CONFIRMED=1
export AAR_START_EVAL_WORKER=1 AAR_EVAL_WORKERS=1 AAR_EVAL_GPUS=4 AAR_EVAL_GPU_CAP=4
export AAR_EVAL_TIME=7-00:00:00 AAR_EVAL_IDLE_SECONDS=604200
export AAR_CHAIN_MAX_HOURS=72 AAR_CHAIN_SANITIZE_ENV=1 AAR_RUNTIME_ENV_DISABLE_FILE=1
export AAR_RESEARCH_ENV_ISOLATION=1 AAR_HIDE_EVAL_CONFIG=1

export AAR_AUTODATA=1 AAR_AUTODATA_LIFECYCLE_SUPERVISED=1
export AAR_AUTODATA_BROKER_RUNNER=local-bwrap AAR_AUTODATA_ENVIRONMENT=oci-runner-firecracker-large
export AAR_AUTODATA_CONCURRENCY="${AAR_RUN13_AUTODATA_CONCURRENCY:-8}"
export AAR_AUTODATA_META_MAX_ITERATIONS=3 AAR_AUTODATA_META_MIN_ITERATIONS=3
export AAR_AUTODATA_META_EARLY_STOP_PATIENCE=3
export AAR_AUTODATA_TUNING_TASKS=64 AAR_AUTODATA_VALIDATION_TASKS=32 AAR_AUTODATA_TEST_TASKS=32
export AAR_AUTODATA_PRODUCTION_ROWS=1000 AAR_AUTODATA_PRODUCTION_INITIAL_TASKS=1250
export AAR_AUTODATA_PRODUCTION_MAX_TASKS=2000
export AAR_AUTODATA_RECIPE_ROOT="${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing"
export AAR_AUTODATA_CHECKOUT="${AUTODATA_CHECKOUT}"
export AAR_AUTODATA_PLUGIN_ROOT="${AUTODATA_CHECKOUT}/plugin/autodata"
export AAR_AUTODATA_SHA="${REQUIRED_AUTODATA_SHA}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_MODEL_ENV_FILE="${CONTROL_ROOT}/secrets/model-api.env"
export AAR_AUTODATA_APPROVAL_PRIVATE_KEY="${CONTROL_ROOT}/secrets/autodata-approval-private.pem"
export AAR_AUTODATA_APPROVAL_PUBLIC_KEY="${CONTROL_ROOT}/metadata/autodata-approval-public.pem"
approval_public_digest="$(sha256sum "${AAR_AUTODATA_APPROVAL_PUBLIC_KEY}" | awk '{print $1}')"
export AAR_AUTODATA_APPROVAL_PUBLIC_KEY_SHA256="sha256:${approval_public_digest}"
export AAR_AUTODATA_APPROVAL_ACTOR=aar-integrity-monitor
export AAR_AUTODATA_APPROVAL_POLICY_VERSION=aar-autodata/run13-full-v1
export AAR_AUTODATA_RESOURCES_READY=1 AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY}"

curl -fsS --noproxy '*' -H 'Host: ram-inference-gateway.ingress.' \
  http://fair-cw-use2-1-ingress-slurm-ingress/v1/models >/dev/null

wait_deployment() {
  local deployment="$1" phase=""
  for _ in $(seq 1 160); do
    phase="$("${SV}/serve.sh" status "${deployment}" --json 2>/dev/null | jq -r '.phase // empty' || true)"
    if [ "${phase}" = serving ]; then
      "${SV}/serve.sh" test "${deployment}" >/dev/null
      return 0
    fi
    case "${phase}" in failed|stopped|expired) return 1;; esac
    sleep 15
  done
  return 1
}

for seed in ${REQUESTED_SEEDS}; do
  incumbent="${CONTROL_ROOT}/chains/${seed}/metadata/incumbent.json"
  deployment="$(jq -r '.endpoint.deployment_id // .deployment_id // empty' "${incumbent}")"
  checkpoint="$(jq -r 'if .schema == "aar.autodata.base-target/v1" then .base_checkpoint else .merged_checkpoint end' "${incumbent}")"
  if [ -z "${deployment}" ] || [ ! -d "${checkpoint}" ]; then
    echo "invalid incumbent target for ${seed}" >&2
    exit 2
  fi
  phase="$("${SV}/serve.sh" status "${deployment}" --json 2>/dev/null | jq -r '.phase // empty' || true)"
  if [ "${phase}" != serving ]; then
    if [ -z "${phase}" ] || [[ "${phase}" =~ ^(failed|stopped|expired)$ ]]; then
      env -u SSL_CERT_FILE -u NODE_EXTRA_CA_CERTS \
        -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
        -u NO_PROXY -u no_proxy \
        "${SV}/serve.sh" deploy "${deployment}" --model gemma-4-31B-it \
          --checkpoint "${checkpoint}" --endpoints 1 --cluster fair-cw-use2-1 \
          --image docker.io/vllm/vllm-openai:v0.25.1 \
          --partition g3 --account ram --qos g3_ram_high \
          --gateway-register --lifetime 7d --no-watch
    fi
    wait_deployment "${deployment}" || { echo "target deployment failed: ${deployment}" >&2; exit 1; }
  else
    "${SV}/serve.sh" test "${deployment}" >/dev/null
  fi
done

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
for seed in ${REQUESTED_SEEDS}; do
  team="${TEAM_DIRS[${seed}]}"
  team_id="$(basename -- "${team}")"
  physical_team="${ARTIFACT_ROOT}/aar_teams/${team_id}"
  chain_root="${CONTROL_ROOT}/chains/${seed}"

  export TEAM_DIR="${physical_team}" AAR_TEAM_ID="${team_id}"
  export LOCAL_FINDINGS_DIR="${physical_team}/forum" SUBMISSIONS_DIR="${physical_team}/submissions"
  export SCORES_DIR="${physical_team}/scores" AAR_IDEAS_DIR="${physical_team}/methods"
  export SESSION_LOGS_DIR="${physical_team}/logs" LIT_FORUM_DIR="${physical_team}/litreview"
  export AAR_RUNTIME_ROOT="${ARTIFACT_ROOT}"
  eval_log="${chain_root}/logs/checkpoint-resume-eval-${timestamp}.txt"
  bash "${REPO}/scripts/launch_eval_worker.sh" "${SUITE_NAME}" "${AAR_EVAL_IDLE_SECONDS}" 1 | tee "${eval_log}"
  evaluator="$(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${eval_log}")"
  [[ "${evaluator}" =~ ^[0-9]+$ ]] || { echo "invalid evaluator job for ${seed}" >&2; exit 1; }

  export AAR_RUNTIME_ROOT="${CONTROL_ROOT}"
  export AAR_AUTODATA_CAMPAIGN_POLICY="${chain_root}/metadata/campaign-policy.json"
  export AAR_AUTODATA_TRAINING_DATA_CONTRACT="${chain_root}/metadata/autodata-training-data-contract.json"
  export AAR_AUTODATA_PROPOSAL_BINDINGS="${chain_root}/secrets/proposal-bindings.json"
  export AAR_VLLM_MERGED_ROOT="${original_checkpoint}/chains/${seed}/merged_candidates"
  AAR_AUTODATA_CAPABILITY="$(<"${chain_root}/secrets/capability")"
  export AAR_AUTODATA_CAPABILITY
  controller="$(sbatch --parsable --output="${team}/logs/checkpoint-resume-controller-%j.out" \
    --export=ALL "${SCRIPT_DIR}/run_13_chain_controller.sbatch" \
    "${seed}" "${team_id}" "${FIRST_JOBS[${seed}]}")"
  controller="${controller%%;*}"
  [[ "${controller}" =~ ^[0-9]+$ ]] || { echo "invalid controller job for ${seed}" >&2; exit 1; }
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${seed}" "${evaluator}" "${controller}" \
    "$(git -C "${REPO}" rev-parse HEAD)" | tee -a "${registry}"
done

printf 'control_root=%s\nartifact_root=%s\nsource_commit=%s\nseeds=%s\n' \
  "${CONTROL_ROOT}" "${ARTIFACT_ROOT}" "$(git -C "${REPO}" rev-parse HEAD)" "${REQUESTED_SEEDS}" \
  > "${CONTROL_ROOT}/metadata/checkpoint-resume-${timestamp}.env"
unset MODEL_API_KEY HF_TOKEN ANTHROPIC_API_KEY AAR_MONITOR_MODEL_API_KEY
echo "[resume] Run 13 evaluators and controllers submitted; artifacts=${ARTIFACT_ROOT}"
