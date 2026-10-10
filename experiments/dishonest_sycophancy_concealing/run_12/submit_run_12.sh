#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
ACTION="${1:-preflight}"
AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER:?}/autodata_pipelines}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
SECRET_ENV="${AAR_RUN12_SECRET_ENV:-/storage/home/${USER}/aar-worktrees/autodata/.env}"
TARGET_URL="${AAR_RUN12_TARGET_URL:-http://fair-cw-use2-1-ingress-slurm-ingress/v1}"
TARGET_HOST_HEADER="${AAR_RUN12_TARGET_HOST_HEADER:-ram-inference-gateway.ingress.}"
TARGET_MODEL="${AAR_RUN12_TARGET_MODEL:-gemma-4-31B-it}"
TARGET_DEPLOYMENT_ID="${AAR_RUN12_TARGET_DEPLOYMENT_ID:-winnieyangwn-run12-gemma4-cshc}"
GENERATOR_URL="${AAR_RUN12_GENERATOR_URL:-http://fair-cw-use2-1-ingress-slurm-ingress/v1}"
GENERATOR_HOST_HEADER="${AAR_RUN12_GENERATOR_HOST_HEADER:-ram-inference-gateway.ingress.}"
GENERATOR_MODEL="${AAR_RUN12_GENERATOR_MODEL:-Kimi-K2.6}"
GENERATOR_DEPLOYMENT_ID="${AAR_RUN12_GENERATOR_DEPLOYMENT_ID:-autodata_8-kimi26}"
INCUMBENT_RUN_ID="${AAR_RUN12_INCUMBENT_RUN_ID:-gemma4_31b-explore-beta-1791334144-gemma4_31b_explore_beta__cshc_v1-1791342624251}"
BASE_CHECKPOINT="/checkpoint/ram/shared/models/google/gemma-4-31B-it"
RUN7_ROOT="/checkpoint/ram/aar/${USER}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run7_attempts/20261007T004406Z-1b3303d02821"
ADAPTER_CHECKPOINT="${AAR_RUN12_ADAPTER_CHECKPOINT:-${RUN7_ROOT}/aar_teams/honesty-sycophancy-concealing-gemma4_31b-opus48-fiveagent-vllm-run7-v0/submissions/${INCUMBENT_RUN_ID}/model}"
MERGED_CHECKPOINT="${AAR_RUN12_MERGED_CHECKPOINT:-${RUN7_ROOT}/merged_candidates/${INCUMBENT_RUN_ID}}"
TARGET_ITERATION="${AAR_RUN12_TARGET_ITERATION:-2}"
PROFILE_CONFIG="${AAR_RUN12_AUTODATA_PROFILE_CONFIG:-${REPO}/configs/autodata/target_aware_local_v1.yaml}"
RUN_CONFIG="${AAR_RUN12_AUTODATA_CANARY_CONFIG:-${SCRIPT_DIR}/autodata_canary.yaml}"

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "Run 12 requires branch autodata" >&2; exit 2; }
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || { echo "tracked AAR worktree is dirty" >&2; exit 2; }
[ -x "${REPO}/.venv/bin/python" ] || { echo "missing HPC AAR environment" >&2; exit 2; }
[ -x "${BROKER_PYTHON}" ] || { echo "missing broker Python" >&2; exit 2; }
config_json="$(PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -m aar.autodata_run_config inspect \
  --profile "${PROFILE_CONFIG}" --run "${RUN_CONFIG}")"
[ "$(jq -r '.target_enabled' <<<"${config_json}")" = true ] || {
  echo "Run 12 canary requires target-aware AutoData YAML" >&2; exit 2;
}
TARGET_MODEL="$(jq -r '.target_model' <<<"${config_json}")"
GENERATOR_URL="$(jq -r '.generator_url' <<<"${config_json}")"
GENERATOR_HOST_HEADER="$(jq -r '.generator_host_header' <<<"${config_json}")"
GENERATOR_MODEL="$(jq -r '.generator_model' <<<"${config_json}")"
GENERATOR_DEPLOYMENT_ID="$(jq -r '.generator_kimi_deployment' <<<"${config_json}")"
RUN12_STORAGE_ROOT="${AAR_RUN12_STORAGE_ROOT:-$(jq -r '.storage_root' <<<"${config_json}")}"
mkdir -p "${RUN12_STORAGE_ROOT}/aar-runs"
RUN12_STORAGE_ROOT="$(realpath -e -- "${RUN12_STORAGE_ROOT}")"
case "${RUN12_STORAGE_ROOT}" in
  /checkpoint/ram/"${USER}") ;;
  *) echo "Run 12 storage root must be /checkpoint/ram/${USER}" >&2; exit 2 ;;
esac
AGENT_BACKEND="$(jq -r '.agent_backend' <<<"${config_json}")"
[ "${AGENT_BACKEND}" = kimi ] || { echo "Run 12 requires agent.backend=kimi" >&2; exit 2; }
export AAR_RUN_STORAGE_ROOT="${RUN12_STORAGE_ROOT}"
export AAR_KEEP_CHECKPOINTS="$(jq -r 'if .keep_checkpoints then "1" else "0" end' <<<"${config_json}")"
export AAR_EVAL_MEM="$(jq -r '.evaluation_memory' <<<"${config_json}")"
export EVAL_MAX_TRUNCATION_RATE="$(jq -r '.max_truncation_rate' <<<"${config_json}")"
export AAR_EXPECTED_MAX_TRUNCATION_RATE="${EVAL_MAX_TRUNCATION_RATE}"
export AAR_AGENT_BACKEND="${AGENT_BACKEND}"
export AAR_KIMI_TURN_TIMEOUT_SECONDS="$(jq -r '.turn_timeout_seconds' <<<"${config_json}")"

if [ "${ACTION}" = preflight ]; then
  attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
  root="${RUN12_STORAGE_ROOT}/aar-runs/run12-adapter-target/${attempt_id}"
  mkdir -p "${root}/secrets"
  chmod 700 "${root}" "${root}/secrets"
  binding="${root}/target-binding.json"
  PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -m aar.autodata_target_binding create \
    --iteration "${TARGET_ITERATION}" \
    --chain-id canary \
    --incumbent-run-id "${INCUMBENT_RUN_ID}" \
    --base-checkpoint "${BASE_CHECKPOINT}" \
    --adapter-checkpoint "${ADAPTER_CHECKPOINT}" \
    --merged-checkpoint "${MERGED_CHECKPOINT}" \
    --target-url "${TARGET_URL}" \
    --target-host-header "${TARGET_HOST_HEADER}" \
    --target-model "${TARGET_MODEL}" \
    --target-deployment-id "${TARGET_DEPLOYMENT_ID}" \
    --output "${binding}"
  export AAR_REPO="${REPO}" AAR_RUN12_ROOT="${root}" AAR_RUN12_TARGET_BINDING="${binding}"
  job_id="$(sbatch --parsable --output="${root}/preflight-%j.out" --export=ALL "${SCRIPT_DIR}/run_12_endpoint_preflight.sbatch")"
  printf 'phase=preflight\njob_id=%s\nroot=%s\naar_git_commit=%s\ntarget_deployment_id=%s\n' \
    "${job_id}" "${root}" "$(git -C "${REPO}" rev-parse HEAD)" "${TARGET_DEPLOYMENT_ID}" \
    | tee "${root}/submission.txt"
  exit 0
fi

if [ "${ACTION}" != canary ] || [ "$#" -ne 2 ]; then
  echo "usage: $0 preflight | $0 canary ATTEMPT_ROOT" >&2
  exit 2
fi
root="$(cd -- "${2}" && pwd)"
case "${root}" in
  /checkpoint/ram/"${USER}"/aar-runs/run12-adapter-target/*) ;;
  *) echo "attempt root is outside the Run 12 artifact directory" >&2; exit 2 ;;
esac
binding="${root}/target-binding.json"
[ -f "${root}/preflight.json" ] || { echo "endpoint preflight has not passed" >&2; exit 2; }
PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -m aar.autodata_target_binding validate "${binding}" >/dev/null
[ -f "${SECRET_ENV}" ] && [ "$(stat -c %a "${SECRET_ENV}")" = 600 ] || { echo "secret env must be mode 600" >&2; exit 2; }
export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
source "${REPO}/scripts/aar_runtime_env.sh"
[ -n "${MODEL_API_KEY:-}" ] || { echo "missing MODEL_API_KEY" >&2; exit 2; }
model_env="${root}/secrets/model-api.env"
printf 'MODEL_API_KEY=%s\n' "${MODEL_API_KEY}" > "${model_env}"
capability_file="${root}/secrets/capability"
"${BROKER_PYTHON}" -c 'import secrets; print(secrets.token_hex(32))' > "${capability_file}"
chmod 600 "${model_env}" "${capability_file}"
policy="${root}/campaign-policy.json"
PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -m aar.autodata_run_config compile \
  --profile "${PROFILE_CONFIG}" --run "${RUN_CONFIG}" \
  --target-binding "${binding}" --chain canary --repo "${REPO}" \
  --output-dir "${root}" >/dev/null
export AAR_AUTODATA_RUNTIME_ENV="${root}/autodata-runtime.env"
# shellcheck disable=SC1090
source "${AAR_AUTODATA_RUNTIME_ENV}"

export AAR_RUN12_ROOT="${root}"
export AAR_RUN12_TARGET_BINDING="${binding}"
export AAR_AUTODATA_CHECKOUT="${AUTODATA_CHECKOUT}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_CAPABILITY_FILE="${capability_file}"
export AAR_AUTODATA_MODEL_ENV_FILE="${model_env}"
export AAR_AUTODATA_CAMPAIGN_POLICY="${policy}"
export AAR_RUN12_GENERATOR_URL="${GENERATOR_URL}"
export AAR_RUN12_GENERATOR_HOST_HEADER="${GENERATOR_HOST_HEADER}"
export AAR_RUN12_GENERATOR_DEPLOYMENT_ID="${GENERATOR_DEPLOYMENT_ID}"
job_id="$(sbatch --parsable --output="${root}/canary-%j.out" --export=ALL "${SCRIPT_DIR}/run_12_target_canary.sbatch")"
printf 'phase=canary\njob_id=%s\naar_git_commit=%s\ngenerator_model=%s\ngenerator_deployment_id=%s\n' \
  "${job_id}" "$(git -C "${REPO}" rev-parse HEAD)" "${GENERATOR_MODEL}" \
  "${GENERATOR_DEPLOYMENT_ID}" | tee -a "${root}/submission.txt"
unset MODEL_API_KEY
