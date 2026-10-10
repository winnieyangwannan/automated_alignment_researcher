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
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
RUNNER="${AAR_AUTODATA_BROKER_RUNNER:-local-bwrap}"
ENVIRONMENT="${AAR_AUTODATA_ENVIRONMENT:-oci-runner-firecracker-large}"
CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:-16}"

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "preflight requires branch autodata" >&2; exit 2; }
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || { echo "tracked AAR worktree is dirty" >&2; exit 2; }
git -C "${AUTODATA_CHECKOUT}" diff --quiet && git -C "${AUTODATA_CHECKOUT}" diff --cached --quiet || { echo "tracked AutoData worktree is dirty" >&2; exit 2; }
[ "$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)" = "${RUN9_REQUIRED_AUTODATA_SHA}" ] || { echo "native preflight requires AutoData ${RUN9_REQUIRED_AUTODATA_SHA}" >&2; exit 2; }
[ "${RUNNER}" = local-bwrap ] || { echo "native preflight requires local-bwrap" >&2; exit 2; }
[ "${CONCURRENCY}" = 16 ] || { echo "native preflight requires production concurrency 16" >&2; exit 2; }
[ -x "${BROKER_PYTHON}" ] || { echo "missing broker Python" >&2; exit 2; }
[ -f "${SECRET_ENV}" ] && [ "$(stat -c %a "${SECRET_ENV}")" = 600 ] || { echo "secret env must be a mode-600 file" >&2; exit 2; }

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
source "${REPO}/scripts/aar_runtime_env.sh"
[ -n "${MODEL_API_KEY:-}" ] || { echo "missing MODEL_API_KEY" >&2; exit 2; }

attempt_id="native-preflight-$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
root="/storage/home/${USER}/aar-runs/run9-five-iteration/${attempt_id}"
mkdir -p "${root}/secrets"
chmod 700 "${root}" "${root}/secrets"
model_env="${root}/secrets/model-api.env"
printf 'MODEL_API_KEY=%s\n' "${MODEL_API_KEY}" > "${model_env}"
capability_file="${root}/secrets/capability"
"${BROKER_PYTHON}" -c 'import secrets; print(secrets.token_hex(32))' > "${capability_file}"
chmod 600 "${model_env}" "${capability_file}"

generator_url="http://fair-cw-use2-1-ingress-slurm-ingress/v1"
generator_host_header="ram-inference-gateway.ingress."
policy="${root}/policy.json"
cat > "${policy}" <<EOF
{
  "schema": "autodata.broker-campaign-policy/v1",
  "campaign_id": "run9-native-lifecycle-preflight",
  "max_cost_usd": "2",
  "runner": "${RUNNER}",
  "environment": "${ENVIRONMENT}",
  "image": "docker.io/library/python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f",
  "expected_image_id": "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316",
  "max_cpus": 2,
  "max_memory_mb": 2048,
  "required_solve_env": {
    "AUTODATA_GENERATOR_URL": "${generator_url}",
    "AUTODATA_GENERATOR_HOST_HEADER": "${generator_host_header}",
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

export AAR_RUN9_PREFLIGHT_ROOT="${root}"
export AAR_AUTODATA_CHECKOUT="${AUTODATA_CHECKOUT}"
export AAR_AUTODATA_PLUGIN_ROOT="${AUTODATA_CHECKOUT}/plugin/autodata"
export AAR_AUTODATA_BROKER_RUNNER="${RUNNER}"
export AAR_AUTODATA_ENVIRONMENT="${ENVIRONMENT}"
export AAR_AUTODATA_CONCURRENCY="${CONCURRENCY}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_CAPABILITY_FILE="${capability_file}"
export AAR_AUTODATA_MODEL_ENV_FILE="${model_env}"
export AAR_AUTODATA_CAMPAIGN_POLICY="${policy}"
export AAR_AUTODATA_GENERATOR_URL="${generator_url}"
export AAR_AUTODATA_GENERATOR_HOST_HEADER="${generator_host_header}"

job_id="$(sbatch --parsable --output="${root}/slurm-%j.out" --export=ALL "${CANARY_DIR}/slurm/preflight.sbatch")"
printf 'job_id=%s\nroot=%s\naar_git_commit=%s\nautodata_git_commit=%s\nconcurrency=%s\n' \
  "${job_id}" "${root}" "$(git -C "${REPO}" rev-parse HEAD)" "$(git -C "${AUTODATA_CHECKOUT}" rev-parse HEAD)" "${CONCURRENCY}" \
  | tee "${root}/submission.txt"
unset MODEL_API_KEY
