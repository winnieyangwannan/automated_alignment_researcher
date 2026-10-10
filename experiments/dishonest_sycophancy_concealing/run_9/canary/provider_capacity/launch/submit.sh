#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CANARY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN_DIR="$(cd -- "${CANARY_DIR}/../.." && pwd)"
REPO="$(cd -- "${RUN_DIR}/../../.." && pwd)"
source "${RUN_DIR}/config/autodata_version.env"
AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER:?}/autodata_pipelines}"
SECRET_ENV="${AAR_RUN9_SECRET_ENV:-/storage/home/${USER}/aar-worktrees/autodata/.env}"
FIRECRACKER_TOKEN="${AAR_RUN9_FIRECRACKER_TOKEN:-/storage/home/${USER}/aar-worktrees/autodata/.sandoq-firecracker-token}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
GENERATOR_DEPLOYMENT="${AAR_AUTODATA_GENERATOR_DEPLOYMENT:-winnieyangwn-kimi26}"
KIMI_PROXY_INFO="${AAR_KIMI_PROXY_INFO:-/checkpoint/ram/shared/vllm_deployments_v2/winnieyangwn-kimi26/proxy_info.json}"
TARGET_BINDING_SOURCE="${AAR_AUTODATA_TARGET_BINDING:-}"
CAPACITY_PROFILE="${AAR_AUTODATA_CAPACITY_PROFILE:-}"
SLURM_DEPENDENCY="${AAR_SLURM_DEPENDENCY:-}"

if [ -n "${TARGET_BINDING_SOURCE}" ] && [ -z "${CAPACITY_PROFILE}" ]; then
  CAPACITY_PROFILE="${CANARY_DIR}/config/run.yaml"
fi
if [ -n "${CAPACITY_PROFILE}" ]; then
  [ -f "${CAPACITY_PROFILE}" ] || { echo "capacity profile is missing: ${CAPACITY_PROFILE}" >&2; exit 2; }
  mapfile -t profile_values < <(
    PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" \
      -m aar.autodata_capacity_profile values --profile "${CAPACITY_PROFILE}"
  )
  [ "${#profile_values[@]}" -eq 5 ] || { echo "capacity profile returned incomplete launch values" >&2; exit 2; }
  RUNNER="${profile_values[0]}"
  ENVIRONMENT="${profile_values[1]}"
  CONCURRENCY="${profile_values[2]}"
  TASK_COUNT="${profile_values[3]}"
  MODEL_REQUEST_MAX_ATTEMPTS="${profile_values[4]}"
  [ -z "${1:-}" ] || [ "${1}" = "${ENVIRONMENT}" ] || {
    echo "positional environment conflicts with YAML capacity profile" >&2
    exit 2
  }
else
  RUNNER="${AAR_AUTODATA_BROKER_RUNNER:-local-bwrap}"
  ENVIRONMENT="${1:-oci-runner-firecracker-medium}"
  CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:-64}"
  TASK_COUNT="${AAR_AUTODATA_CANARY_TASK_COUNT:-${CONCURRENCY}}"
  MODEL_REQUEST_MAX_ATTEMPTS="${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS:-1}"
fi

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
case "${TASK_COUNT}" in
  ''|*[!0-9]*|0) echo "capacity-canary task count must be in [concurrency,512]" >&2; exit 2 ;;
esac
[ "${TASK_COUNT}" -ge "${CONCURRENCY}" ] && [ "${TASK_COUNT}" -le 512 ] || {
  echo "capacity-canary task count must be in [concurrency,512]" >&2
  exit 2
}
case "${MODEL_REQUEST_MAX_ATTEMPTS}" in
  1|2|3|4|5) ;;
  *) echo "model request max attempts must be in [1,5]" >&2; exit 2 ;;
esac
[[ "${GENERATOR_DEPLOYMENT}" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "invalid generator deployment id: ${GENERATOR_DEPLOYMENT}" >&2
  exit 2
}
if [ -n "${SLURM_DEPENDENCY}" ] && [[ ! "${SLURM_DEPENDENCY}" =~ ^after(any|ok):[0-9]+$ ]]; then
  echo "capacity-canary dependency must be afterany:<job-id> or afterok:<job-id>" >&2
  exit 2
fi
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
if [ -n "${TARGET_BINDING_SOURCE}" ]; then
  [ -f "${TARGET_BINDING_SOURCE}" ] || { echo "target binding is missing" >&2; exit 2; }
  PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -m aar.autodata_target_binding \
    validate "${TARGET_BINDING_SOURCE}" >/dev/null
fi
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
target_binding=""
if [ -n "${TARGET_BINDING_SOURCE}" ]; then
  target_binding="${root}/target-binding.json"
  install -m 600 "${TARGET_BINDING_SOURCE}" "${target_binding}"
fi
chmod 600 "${model_env}" "${capability_file}"

policy="${root}/policy.json"
if [ -n "${CAPACITY_PROFILE}" ]; then
  [ -n "${target_binding}" ] || { echo "target-aware capacity profile requires a target binding" >&2; exit 2; }
  PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" \
    -m aar.autodata_capacity_profile render-policy \
    --profile "${CAPACITY_PROFILE}" \
    --campaign-id "run9-${RUNNER}-capacity-canary" \
    --generator-url "${GENERATOR_URL}" \
    --generator-host-header "${GENERATOR_HOST_HEADER}" \
    --generator-deployment-id "${GENERATOR_DEPLOYMENT}" \
    --target-binding "${target_binding}" \
    --output "${policy}"
else
  cat > "${policy}" <<EOF
{
  "schema": "autodata.broker-campaign-policy/v1",
  "campaign_id": "run9-${RUNNER}-capacity-canary",
  "max_cost_usd": "10",
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
    "AUTODATA_GENERATOR_DEPLOYMENT_ID": "${GENERATOR_DEPLOYMENT}",
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
    "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "${MODEL_REQUEST_MAX_ATTEMPTS}"
  }
}
EOF
  if [ -n "${target_binding}" ]; then
    PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" - \
      "${target_binding}" "${policy}" <<'PY'
import json
import pathlib
import sys

from aar.autodata_target_binding import load_binding

binding = load_binding(pathlib.Path(sys.argv[1]))
path = pathlib.Path(sys.argv[2])
policy = json.loads(path.read_text(encoding="utf-8"))
policy["required_solve_env"].update(
    {
        **binding.solve_environment(),
        "AUTODATA_TARGET_MAX_INPUT": "8192",
        "AUTODATA_TARGET_MAX_OUTPUT": "512",
        "AUTODATA_TARGET_TIMEOUT": "90",
        "AUTODATA_TARGET_INPUT_USD_PER_MILLION": "0",
        "AUTODATA_TARGET_OUTPUT_USD_PER_MILLION": "0",
    }
)
path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
  fi
fi

export AAR_RUN9_CANARY_ROOT="${root}"
export AAR_AUTODATA_CHECKOUT="${AUTODATA_CHECKOUT}"
export AAR_AUTODATA_BROKER_RUNNER="${RUNNER}"
export AAR_AUTODATA_GENERATOR_URL="${GENERATOR_URL}"
export AAR_AUTODATA_GENERATOR_HOST_HEADER="${GENERATOR_HOST_HEADER}"
export AAR_AUTODATA_ENVIRONMENT="${ENVIRONMENT}"
export AAR_AUTODATA_CONCURRENCY="${CONCURRENCY}"
export AAR_AUTODATA_CANARY_TASK_COUNT="${TASK_COUNT}"
export AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS="${MODEL_REQUEST_MAX_ATTEMPTS}"
export AAR_AUTODATA_GENERATOR_DEPLOYMENT="${GENERATOR_DEPLOYMENT}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_CAPABILITY_FILE="${capability_file}"
export AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE="${FIRECRACKER_TOKEN}"
export AAR_AUTODATA_MODEL_ENV_FILE="${model_env}"
export AAR_AUTODATA_CAMPAIGN_POLICY="${policy}"
export AAR_KIMI_PROXY_INFO="${kimi_proxy_info}"
export AAR_AUTODATA_TARGET_BINDING="${target_binding}"
export AAR_AUTODATA_CAPACITY_PROFILE="${CAPACITY_PROFILE}"

sbatch_args=(--parsable --output="${root}/slurm-%j.out" --export=ALL)
if [ -n "${SLURM_DEPENDENCY}" ]; then
  sbatch_args+=(--dependency="${SLURM_DEPENDENCY}")
fi
job_id="$(sbatch "${sbatch_args[@]}" "${CANARY_DIR}/slurm/capacity.sbatch")"
printf 'job_id=%s\nroot=%s\nbroker_runner=%s\nenvironment=%s\nconcurrency=%s\ntask_count=%s\nmodel_request_max_attempts=%s\ngenerator_deployment_id=%s\ncapacity_profile=%s\ntarget_aware=%s\naar_git_commit=%s\nautodata_git_commit=%s\n' \
  "${job_id}" "${root}" "${RUNNER}" "${ENVIRONMENT}" "${CONCURRENCY}" "${TASK_COUNT}" "${MODEL_REQUEST_MAX_ATTEMPTS}" "${GENERATOR_DEPLOYMENT}" "${CAPACITY_PROFILE}" "$([ -n "${target_binding}" ] && printf true || printf false)" "$(git -C "${REPO}" rev-parse HEAD)" "$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)" \
  | tee "${root}/submission.txt"
unset MODEL_API_KEY
