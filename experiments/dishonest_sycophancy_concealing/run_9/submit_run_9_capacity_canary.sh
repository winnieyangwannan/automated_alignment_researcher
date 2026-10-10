#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
source "${SCRIPT_DIR}/autodata_version.env"
AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER:?}/autodata_pipelines}"
SECRET_ENV="${AAR_RUN9_SECRET_ENV:-/storage/home/${USER}/aar-worktrees/autodata/.env}"
FIRECRACKER_TOKEN="${AAR_RUN9_FIRECRACKER_TOKEN:-/storage/home/${USER}/aar-worktrees/autodata/.sandoq-firecracker-token}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
RUNNER="${AAR_AUTODATA_BROKER_RUNNER:-local-bwrap}"
ENVIRONMENT="${1:-oci-runner-firecracker-medium}"
CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:-24}"
KIMI_PROXY_INFO="${AAR_KIMI_PROXY_INFO:-/checkpoint/ram/shared/vllm_deployments_v2/winnieyangwn-kimi26/proxy_info.json}"

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "canary requires branch autodata" >&2; exit 2; }
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || { echo "tracked AAR worktree is dirty" >&2; exit 2; }
git -C "${AUTODATA_CHECKOUT}" diff --quiet && git -C "${AUTODATA_CHECKOUT}" diff --cached --quiet || { echo "tracked AutoData worktree is dirty" >&2; exit 2; }
[ "$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)" = "${RUN9_REQUIRED_AUTODATA_SHA}" ] || { echo "capacity canary requires AutoData ${RUN9_REQUIRED_AUTODATA_SHA}" >&2; exit 2; }
case "${ENVIRONMENT}" in
  oci-runner-firecracker-small|oci-runner-firecracker-medium|oci-runner-firecracker-large|oci-runner-firecracker-xlarge) ;;
  *) echo "unsupported AutoData Firecracker environment: ${ENVIRONMENT}" >&2; exit 2 ;;
esac
case "${RUNNER}" in
  local-bwrap|sandoq-firecracker) ;;
  *) echo "unsupported AutoData broker runner: ${RUNNER}" >&2; exit 2 ;;
esac
case "${CONCURRENCY}" in
  ''|*[!0-9]*|0) echo "capacity-canary concurrency must be in [1,64]" >&2; exit 2 ;;
esac
[ "${CONCURRENCY}" -le 64 ] || { echo "capacity-canary concurrency must be in [1,64]" >&2; exit 2; }
if [ "${RUNNER}" = local-bwrap ]; then
  GENERATOR_URL="http://fair-cw-use2-1-ingress-slurm-ingress/v1"
  GENERATOR_HOST_HEADER="ram-inference-gateway.ingress."
else
  GENERATOR_URL="https://ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud/v1"
  GENERATOR_HOST_HEADER="ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud"
fi
for required in "${SECRET_ENV}" "${KIMI_PROXY_INFO}"; do
  [ -f "${required}" ] || { echo "missing required input: ${required}" >&2; exit 2; }
done
[ "$(stat -c %a "${SECRET_ENV}")" = 600 ] || { echo "secret env must be mode 600" >&2; exit 2; }
if [ "${RUNNER}" = sandoq-firecracker ]; then
  [ -f "${FIRECRACKER_TOKEN}" ] || { echo "missing Firecracker token" >&2; exit 2; }
  [ "$(stat -c %a "${FIRECRACKER_TOKEN}")" = 600 ] || { echo "Firecracker token must be mode 600" >&2; exit 2; }
fi
[ -x "${BROKER_PYTHON}" ] || { echo "missing broker Python" >&2; exit 2; }

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
source "${REPO}/scripts/aar_runtime_env.sh"
[ -n "${MODEL_API_KEY:-}" ] || { echo "missing MODEL_API_KEY" >&2; exit 2; }

attempt_id="capacity-$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
root="/storage/home/${USER}/aar-runs/run9-five-iteration/${attempt_id}"
mkdir -p "${root}/secrets"
chmod 700 "${root}" "${root}/secrets"
model_env="${root}/secrets/model-api.env"
printf 'MODEL_API_KEY=%s\n' "${MODEL_API_KEY}" > "${model_env}"
capability_file="${root}/secrets/capability"
"${BROKER_PYTHON}" -c 'import secrets; print(secrets.token_hex(32))' > "${capability_file}"
kimi_proxy_info="${root}/secrets/kimi-proxy-info.json"
install -m 600 "${KIMI_PROXY_INFO}" "${kimi_proxy_info}"
chmod 600 "${model_env}" "${capability_file}"

policy="${root}/policy.json"
cat > "${policy}" <<EOF
{
  "schema": "autodata.broker-campaign-policy/v1",
  "campaign_id": "run9-${RUNNER}-capacity-canary",
  "max_cost_usd": "2",
  "runner": "${RUNNER}",
  "environment": "${ENVIRONMENT}",
  "image": "docker.io/library/python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f",
  "expected_image_id": "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316",
  "max_cpus": 2,
  "max_memory_mb": 2048,
  "required_solve_env": {
    "AUTODATA_GENERATOR_URL": "${GENERATOR_URL}",
    "AUTODATA_GENERATOR_HOST_HEADER": "${GENERATOR_HOST_HEADER}",
    "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
    "AUTODATA_GENERATOR_DEPLOYMENT_ID": "winnieyangwn-kimi26",
    "AUTODATA_GENERATOR_MAX_INPUT": "4096",
    "AUTODATA_GENERATOR_MAX_OUTPUT": "768",
    "AUTODATA_GENERATOR_TIMEOUT": "90",
    "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
    "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
    "AUTODATA_JUDGE_URL": "https://api.meta.ai/v1/responses",
    "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
    "AUTODATA_JUDGE_MAX_INPUT": "4096",
    "AUTODATA_JUDGE_MAX_OUTPUT": "512",
    "AUTODATA_JUDGE_TIMEOUT": "90",
    "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
    "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "4",
    "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "1"
  }
}
EOF

export AAR_RUN9_CANARY_ROOT="${root}"
export AAR_AUTODATA_CHECKOUT="${AUTODATA_CHECKOUT}"
export AAR_AUTODATA_BROKER_RUNNER="${RUNNER}"
export AAR_AUTODATA_GENERATOR_URL="${GENERATOR_URL}"
export AAR_AUTODATA_GENERATOR_HOST_HEADER="${GENERATOR_HOST_HEADER}"
export AAR_AUTODATA_ENVIRONMENT="${ENVIRONMENT}"
export AAR_AUTODATA_CONCURRENCY="${CONCURRENCY}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_CAPABILITY_FILE="${capability_file}"
export AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE="${FIRECRACKER_TOKEN}"
export AAR_AUTODATA_MODEL_ENV_FILE="${model_env}"
export AAR_AUTODATA_CAMPAIGN_POLICY="${policy}"
export AAR_KIMI_PROXY_INFO="${kimi_proxy_info}"

job_id="$(sbatch --parsable --output="${root}/slurm-%j.out" --export=ALL "${SCRIPT_DIR}/run_9_capacity_canary.sbatch")"
printf 'job_id=%s\nroot=%s\nbroker_runner=%s\nenvironment=%s\nconcurrency=%s\naar_git_commit=%s\nautodata_git_commit=%s\n' \
  "${job_id}" "${root}" "${RUNNER}" "${ENVIRONMENT}" "${CONCURRENCY}" "$(git -C "${REPO}" rev-parse HEAD)" "$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)" \
  | tee "${root}/submission.txt"
unset MODEL_API_KEY
