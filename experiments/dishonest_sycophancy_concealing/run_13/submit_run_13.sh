#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
ACTION="${1:-preflight}"
AUTODATA_CHECKOUT="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER:?}/autodata_pipelines}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
SECRET_ENV="${AAR_RUN13_SECRET_ENV:-/storage/home/${USER}/aar-worktrees/autodata/.env}"
TARGET_URL="${AAR_RUN13_TARGET_URL:-http://fair-cw-use2-1-ingress-slurm-ingress/v1}"
TARGET_HOST_HEADER="${AAR_RUN13_TARGET_HOST_HEADER:-ram-inference-gateway.ingress.}"
TARGET_MODEL="${AAR_RUN13_TARGET_MODEL:-gemma-4-31B-it}"
TARGET_DEPLOYMENT_ID="${AAR_RUN13_TARGET_DEPLOYMENT_ID:-winnieyangwn-run13-gemma4-cshc}"
GENERATOR_URL="${AAR_RUN13_GENERATOR_URL:-http://fair-cw-use2-1-ingress-slurm-ingress/v1}"
GENERATOR_HOST_HEADER="${AAR_RUN13_GENERATOR_HOST_HEADER:-ram-inference-gateway.ingress.}"
GENERATOR_MODEL="${AAR_RUN13_GENERATOR_MODEL:-Kimi-K2.6}"
GENERATOR_DEPLOYMENT_ID="${AAR_RUN13_GENERATOR_DEPLOYMENT_ID:-aar_8-kimi26}"
INCUMBENT_RUN_ID="gemma4_31b-explore-beta-1791334144-gemma4_31b_explore_beta__cshc_v1-1791342624251"
BASE_CHECKPOINT="/checkpoint/ram/shared/models/google/gemma-4-31B-it"
RUN7_ROOT="/checkpoint/ram/aar/${USER}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0/run7_attempts/20261007T004406Z-1b3303d02821"
ADAPTER_CHECKPOINT="${RUN7_ROOT}/aar_teams/honesty-sycophancy-concealing-gemma4_31b-opus48-fiveagent-vllm-run7-v0/submissions/${INCUMBENT_RUN_ID}/model"
MERGED_CHECKPOINT="${RUN7_ROOT}/merged_candidates/${INCUMBENT_RUN_ID}"

export AAR_AGENT_BACKEND=claude
export AAR_AGENT_MODEL=claude-opus-4-8

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "Run 13 requires branch autodata" >&2; exit 2; }
git -C "${REPO}" diff --quiet && git -C "${REPO}" diff --cached --quiet || { echo "tracked AAR worktree is dirty" >&2; exit 2; }
[ -x "${REPO}/.venv/bin/python" ] || { echo "missing HPC AAR environment" >&2; exit 2; }
[ -x "${BROKER_PYTHON}" ] || { echo "missing broker Python" >&2; exit 2; }
[ "${AAR_AGENT_BACKEND}" = claude ] || { echo "Run 13 requires Claude backend" >&2; exit 2; }
[ "${AAR_AGENT_MODEL}" = claude-opus-4-8 ] || { echo "Run 13 requires Claude Opus 4.8" >&2; exit 2; }

if [ "${ACTION}" = preflight ]; then
  attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
  root="/storage/home/${USER}/aar-runs/run13-adapter-target/${attempt_id}"
  mkdir -p "${root}/secrets"
  chmod 700 "${root}" "${root}/secrets"
  binding="${root}/target-binding.json"
  PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" -m aar.autodata_target_binding create \
    --iteration 2 \
    --incumbent-run-id "${INCUMBENT_RUN_ID}" \
    --base-checkpoint "${BASE_CHECKPOINT}" \
    --adapter-checkpoint "${ADAPTER_CHECKPOINT}" \
    --merged-checkpoint "${MERGED_CHECKPOINT}" \
    --target-url "${TARGET_URL}" \
    --target-host-header "${TARGET_HOST_HEADER}" \
    --target-model "${TARGET_MODEL}" \
    --target-deployment-id "${TARGET_DEPLOYMENT_ID}" \
    --output "${binding}"
  export AAR_REPO="${REPO}" AAR_RUN13_ROOT="${root}" AAR_RUN13_TARGET_BINDING="${binding}"
  job_id="$(sbatch --parsable --output="${root}/preflight-%j.out" --export=ALL "${SCRIPT_DIR}/run_13_endpoint_preflight.sbatch")"
  printf 'phase=preflight\njob_id=%s\nroot=%s\naar_git_commit=%s\nresearch_backend=%s\nresearch_model=%s\ntarget_deployment_id=%s\n' \
    "${job_id}" "${root}" "$(git -C "${REPO}" rev-parse HEAD)" "${AAR_AGENT_BACKEND}" \
    "${AAR_AGENT_MODEL}" "${TARGET_DEPLOYMENT_ID}" | tee "${root}/submission.txt"
  exit 0
fi

if [ "${ACTION}" != canary ] || [ "$#" -ne 2 ]; then
  echo "usage: $0 preflight | $0 canary ATTEMPT_ROOT" >&2
  exit 2
fi
root="$(cd -- "${2}" && pwd)"
case "${root}" in
  /storage/home/"${USER}"/aar-runs/run13-adapter-target/*) ;;
  *) echo "attempt root is outside the Run 13 artifact directory" >&2; exit 2 ;;
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
PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" - \
  "${binding}" "${policy}" "${GENERATOR_URL}" "${GENERATOR_HOST_HEADER}" \
  "${GENERATOR_MODEL}" "${GENERATOR_DEPLOYMENT_ID}" <<'PY'
import json
import os
import pathlib
import sys
import tempfile

from aar.autodata_target_binding import load_binding

binding = load_binding(pathlib.Path(sys.argv[1]))
required = {
    "AUTODATA_GENERATOR_URL": sys.argv[3],
    "AUTODATA_GENERATOR_HOST_HEADER": sys.argv[4],
    "AUTODATA_GENERATOR_MODEL": sys.argv[5],
    "AUTODATA_GENERATOR_DEPLOYMENT_ID": sys.argv[6],
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
    "AUTODATA_TARGET_MAX_INPUT": "8192",
    "AUTODATA_TARGET_MAX_OUTPUT": "512",
    "AUTODATA_TARGET_TIMEOUT": "90",
    "AUTODATA_TARGET_INPUT_USD_PER_MILLION": "0",
    "AUTODATA_TARGET_OUTPUT_USD_PER_MILLION": "0",
    "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "1",
    **binding.solve_environment(),
}
policy = {
    "schema": "autodata.broker-campaign-policy/v1",
    "campaign_id": "run13-adapter-target-canary",
    "max_cost_usd": "1",
    "runner": "local-bwrap",
    "environment": "oci-runner-firecracker-large",
    "image": "docker.io/library/python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f",
    "expected_image_id": "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316",
    "max_cpus": 2,
    "max_memory_mb": 2048,
    "required_solve_env": required,
}
output = pathlib.Path(sys.argv[2])
descriptor, name = tempfile.mkstemp(prefix=".policy.", suffix=".tmp", dir=output.parent)
temporary = pathlib.Path(name)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(policy, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
finally:
    temporary.unlink(missing_ok=True)
PY

export AAR_RUN13_ROOT="${root}"
export AAR_RUN13_TARGET_BINDING="${binding}"
export AAR_AUTODATA_CHECKOUT="${AUTODATA_CHECKOUT}"
export AAR_AUTODATA_BROKER_PYTHON="${BROKER_PYTHON}"
export AAR_AUTODATA_CAPABILITY_FILE="${capability_file}"
export AAR_AUTODATA_MODEL_ENV_FILE="${model_env}"
export AAR_AUTODATA_CAMPAIGN_POLICY="${policy}"
export AAR_RUN13_GENERATOR_URL="${GENERATOR_URL}"
export AAR_RUN13_GENERATOR_HOST_HEADER="${GENERATOR_HOST_HEADER}"
export AAR_RUN13_GENERATOR_DEPLOYMENT_ID="${GENERATOR_DEPLOYMENT_ID}"
job_id="$(sbatch --parsable --output="${root}/canary-%j.out" --export=ALL "${SCRIPT_DIR}/run_13_target_canary.sbatch")"
printf 'phase=canary\njob_id=%s\naar_git_commit=%s\ngenerator_model=%s\ngenerator_deployment_id=%s\n' \
  "${job_id}" "$(git -C "${REPO}" rev-parse HEAD)" "${GENERATOR_MODEL}" \
  "${GENERATOR_DEPLOYMENT_ID}" | tee -a "${root}/submission.txt"
unset MODEL_API_KEY
