#!/bin/bash
# Submit one sequential two-iteration Run 8 chain, its evaluator, and live
# AutoData services. This submitter creates retained state but never copies a
# secret value into the checkout or Slurm's exported environment.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
EXPECTED_BRANCH=autodata
AUTODATA_SHA=9e623eb25bab4c4ba50642f72ca338f887772e27
AUTODATA_ROOT="${AAR_RUN8_AUTODATA_ROOT:-/storage/home/winnieyangwn/autodata_pipelines}"
BROKER_PYTHON="${AAR_RUN8_BROKER_PYTHON:-/storage/home/winnieyangwn/ram_common/sandoq_fleet/.venv-x86_64/bin/python}"
SERVE_API_V2="${AAR_RUN8_SERVE_API_V2:-${RAM_COMMON_ROOT:-${HOME}}/ram_common/vllm_tools/serve_api_v2/serve.sh}"
VLLM_WORKER_DEPLOYMENT_ID=winnieyangwn-gemma-4-31B-it
VLLM_WORKER_SH="/checkpoint/ram/shared/vllm_deployments_v2/${VLLM_WORKER_DEPLOYMENT_ID}/src/serve_api_v2/worker/worker_vllm.sh"
REUSED_BASELINE="${1:-/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/20261005T083040Z-ab488b75137b-reuse/metadata/gemma4_31b_multidimensional_baseline.json}"
SECRET_ENV="${AAR_RUN8_SECRET_ENV:-${REPO}/.env}"
EXECSIDECAR_TOKEN_FILE=/storage/home/winnieyangwn/aar-worktrees/autodata/.sandoq-firecracker-token

AUTODATA_MAX_COST_USD=100
AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD="${AAR_RUN8_AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD:-0.05}"
AUTODATA_REQUIRED_RETAINED_ROWS=64
GENERATOR_INPUT_RATE="${AAR_RUN8_GENERATOR_INPUT_USD_PER_MILLION:-1}"
GENERATOR_OUTPUT_RATE="${AAR_RUN8_GENERATOR_OUTPUT_USD_PER_MILLION:-4}"
JUDGE_INPUT_RATE="${AAR_RUN8_JUDGE_INPUT_USD_PER_MILLION:-1}"
JUDGE_OUTPUT_RATE="${AAR_RUN8_JUDGE_OUTPUT_USD_PER_MILLION:-4}"
GENERATOR_URL=https://ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud/v1
RUN8_STORAGE_ROOT="${AAR_RUN8_STORAGE_ROOT:-/storage/home/${USER:?}/aar-runs}"

[ "${USER}" = "$(id -un)" ] || {
  echo "run 8 USER must match the submitting account" >&2
  exit 2
}

require_mode_0600() {
  local name="$1" path="$2" mode owner
  if [ ! -f "${path}" ] || [ -L "${path}" ]; then
    echo "run 8 requires ${name} to be a regular, non-symlink file: ${path}" >&2
    exit 2
  fi
  mode="$(stat -c '%a' -- "${path}")"
  owner="$(stat -c '%u' -- "${path}")"
  if [ "${mode}" != 600 ] || [ "${owner}" != "$(id -u)" ]; then
    echo "run 8 requires ${name} to be owned by the submitting user and mode 0600" >&2
    exit 2
  fi
  [ -s "${path}" ] || { echo "run 8 requires nonempty ${name}" >&2; exit 2; }
}

safe_export_value() {
  case "$2" in
    *','*|*$'\n'*|*$'\r'*)
      echo "run 8 cannot pass $1 through Slurm because it contains a comma or newline" >&2
      exit 2
      ;;
  esac
}

[ "$(git -C "${REPO}" branch --show-current)" = "${EXPECTED_BRANCH}" ] || {
  echo "run 8 requires branch ${EXPECTED_BRANCH}" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "run 8 requires a clean tracked worktree" >&2
  exit 2
fi
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all -- \
  aar benchmark_docs scripts replication pyproject.toml uv.lock \
  experiments/dishonest_sycophancy_concealing/run_8)" ]; then
  echo "run 8 refuses untracked or modified launch-critical files" >&2
  exit 2
fi
[ -x "${REPO}/.venv/bin/python" ] || {
  echo "run 8 requires its worktree-local ARM64 environment at ${REPO}/.venv" >&2
  exit 2
}
"${REPO}/.venv/bin/python" -c \
  'import platform; assert platform.machine() == "aarch64"' || {
  echo "run 8 host orchestration environment is not ARM64" >&2
  exit 2
}

AUTODATA_ROOT="$(realpath -e -- "${AUTODATA_ROOT}")"
[ "$(git -C "${AUTODATA_ROOT}" branch --show-current)" = main ] || {
  echo "run 8 requires the canonical AutoData checkout on main" >&2
  exit 2
}
[ "$(git -C "${AUTODATA_ROOT}" rev-parse HEAD)" = "${AUTODATA_SHA}" ] || {
  echo "run 8 requires canonical AutoData commit ${AUTODATA_SHA}" >&2
  exit 2
}
[ -z "$(git -C "${AUTODATA_ROOT}" status --porcelain --untracked-files=all)" ] || {
  echo "run 8 requires a clean canonical AutoData checkout" >&2
  exit 2
}
[ -x "${BROKER_PYTHON}" ] || { echo "run 8 broker Python is not executable" >&2; exit 2; }
PYTHONPATH="${AUTODATA_ROOT}/src" "${BROKER_PYTHON}" -c \
  'import aiohttp, autodata, sandoq_client' || {
  echo "run 8 broker Python lacks the canonical AutoData broker dependencies" >&2
  exit 2
}

[ ! -L "${SECRET_ENV}" ] || { echo "run 8 refuses a symlink secret environment" >&2; exit 2; }
[ ! -L "${EXECSIDECAR_TOKEN_FILE}" ] || { echo "run 8 refuses a symlink execsidecar token" >&2; exit 2; }
SECRET_ENV="$(realpath -e -- "${SECRET_ENV}")"
EXECSIDECAR_TOKEN_FILE="$(realpath -e -- "${EXECSIDECAR_TOKEN_FILE}")"
case "${SECRET_ENV}" in
  "/storage/home/${USER}"|"/storage/home/${USER}/"*) ;;
  *)
    echo "run 8 requires HARNESS_ENV inside /storage/home/${USER} so the research sandbox can hide it" >&2
    exit 2
    ;;
esac
require_mode_0600 HARNESS_ENV "${SECRET_ENV}"
require_mode_0600 execsidecar-token "${EXECSIDECAR_TOKEN_FILE}"

export AAR_REPO="${REPO}"
export HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || {
    echo "run 8 requires nonempty ${secret_name} in ${HARNESS_ENV}" >&2
    exit 2
  }
done

source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${source_root}" --verify-only >/dev/null || {
  echo "run 8 requires the pinned LLM-Uncertainty-Bench source" >&2
  exit 2
}
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"

REUSED_BASELINE="$(realpath -e -- "${REUSED_BASELINE}")"
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" >/dev/null

# A production target must be distinct from both retained smoke sizes. The cap
# must cover two complete worst-case reservations because the service uses one
# durable scope for both sequential proposal run IDs.
"${REPO}/.venv/bin/python" - \
  "${AUTODATA_MAX_COST_USD}" \
  "${AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD}" \
  "${AUTODATA_REQUIRED_RETAINED_ROWS}" \
  "${GENERATOR_INPUT_RATE}" "${GENERATOR_OUTPUT_RATE}" \
  "${JUDGE_INPUT_RATE}" "${JUDGE_OUTPUT_RATE}" <<'PY'
from decimal import Decimal, InvalidOperation
import sys

names = (
    "campaign cap",
    "maximum estimated cost per task",
    "retained rows",
    "Kimi input rate",
    "Kimi output rate",
    "Luna input rate",
    "Luna output rate",
)
try:
    cap = Decimal(sys.argv[1])
    per_task = Decimal(sys.argv[2])
    rows = int(sys.argv[3])
    rates = [Decimal(value) for value in sys.argv[4:]]
except (InvalidOperation, ValueError) as error:
    raise SystemExit(f"invalid Run 8 production control: {error}")
if not cap.is_finite() or cap <= 0:
    raise SystemExit(f"{names[0]} must be a positive finite decimal")
if not per_task.is_finite() or per_task <= 0:
    raise SystemExit(f"{names[1]} must be a positive finite decimal")
if rows <= 16 or str(rows) != sys.argv[3]:
    raise SystemExit("retained rows must be an integer greater than the 16-row smoke target")
if any(not rate.is_finite() or rate <= 0 for rate in rates):
    raise SystemExit("all Kimi and Luna token rates must be positive finite decimals")
source_count = max(96, (rows * 4 + 2) // 3)
task_attempts = 2 + 2 * 64 + 3 * 32 + 7 * source_count
required_cap = Decimal(2 * task_attempts) * per_task
if cap < required_cap:
    raise SystemExit(
        f"campaign cap {cap} cannot cover two conservative reservations totaling {required_cap}"
    )
PY

# Verify the exact deployment on every submission without retaining or using
# its ephemeral direct proxy. Firecracker tasks use the stable qualified pod
# gateway and X-Deployment-Id instead.
deployment_json="$("${SERVE_API_V2}" status winnieyangwn-kimi26 --json)"
printf '%s' "${deployment_json}" | "${REPO}/.venv/bin/python" -c '
import json, sys
value = json.load(sys.stdin)
if value.get("phase") != "serving":
    raise SystemExit("Kimi deployment is not serving")
if value.get("spec", {}).get("served_model_name") != "Kimi-K2.6":
    raise SystemExit("Kimi deployment serves the wrong model")
if int(value.get("endpoints_summary", {}).get("ready", 0)) < 1:
    raise SystemExit("Kimi deployment has no ready endpoint")
'

# Candidate evaluation launches a fresh vLLM worker for every atomically merged
# checkpoint. Reuse the immutable source snapshot retained by the live,
# user-owned Gemma deployment, and fail before creating an attempt if that
# snapshot is no longer available. This is a read-only execution input; Run 8
# outputs remain confined to RUN8_STORAGE_ROOT.
[ -x "${VLLM_WORKER_SH}" ] || {
  echo "run 8 requires the validated Gemma vLLM worker: ${VLLM_WORKER_SH}" >&2
  exit 2
}
gemma_deployment_json="$("${SERVE_API_V2}" status "${VLLM_WORKER_DEPLOYMENT_ID}" --json)"
printf '%s' "${gemma_deployment_json}" | "${REPO}/.venv/bin/python" -c '
import json, sys
value = json.load(sys.stdin)
if value.get("phase") != "serving":
    raise SystemExit("Gemma worker-source deployment is not serving")
if value.get("spec", {}).get("served_model_name") != "gemma-4-31B-it":
    raise SystemExit("Gemma worker-source deployment serves the wrong model")
if int(value.get("endpoints_summary", {}).get("ready", 0)) < 1:
    raise SystemExit("Gemma worker-source deployment has no ready endpoint")
'

gateway_json="$(curl -fsS --noproxy '*' -H 'Host: ram-inference-gateway.ingress.' \
  http://fair-cw-use2-1-ingress-slurm-ingress/v1/models)"
printf '%s' "${gateway_json}" | "${REPO}/.venv/bin/python" -c '
import json, sys
models = json.load(sys.stdin).get("data", [])
if not any(item.get("id") == "Kimi-K2.6" and item.get("deployment") == "winnieyangwn-kimi26" for item in models):
    raise SystemExit("qualified Kimi deployment is absent from the fair-cw-use2-1 gateway")
'

commit="$(git -C "${REPO}" rev-parse HEAD)"
short_commit="$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}"
RUN8_STORAGE_ROOT="$(realpath -m -- "${RUN8_STORAGE_ROOT}")"
case "${RUN8_STORAGE_ROOT}" in
  "/storage/home/${USER}/aar-runs"|"/storage/home/${USER}/aar-runs/"*) ;;
  *)
    echo "run 8 artifact root must stay inside /storage/home/${USER}/aar-runs: ${RUN8_STORAGE_ROOT}" >&2
    exit 2
    ;;
esac
mkdir -p "${RUN8_STORAGE_ROOT}"
RUN8_STORAGE_ROOT="$(realpath -e -- "${RUN8_STORAGE_ROOT}")"
case "${RUN8_STORAGE_ROOT}" in
  "/storage/home/${USER}/aar-runs"|"/storage/home/${USER}/aar-runs/"*) ;;
  *)
    echo "run 8 artifact root must stay inside /storage/home/${USER}/aar-runs: ${RUN8_STORAGE_ROOT}" >&2
    exit 2
    ;;
esac
case "${RUN8_STORAGE_ROOT}" in
  /checkpoint/ram|/checkpoint/ram/*)
    echo "run 8 refuses to store new artifacts under /checkpoint/ram" >&2
    exit 2
    ;;
esac
artifact_base="${RUN8_STORAGE_ROOT}/honesty-sycophancy-concealing-gemma4-31b-vllm-v0"
[ ! -L "${artifact_base}" ] || {
  echo "run 8 refuses a symlink artifact base: ${artifact_base}" >&2
  exit 2
}
mkdir -p "${artifact_base}"
artifact_base="$(realpath -e -- "${artifact_base}")"
case "${artifact_base}" in
  "${RUN8_STORAGE_ROOT}"/*) ;;
  *) echo "run 8 artifact base escaped the validated root: ${artifact_base}" >&2; exit 2 ;;
esac
attempt_parent="${artifact_base}/run8_attempts"
[ ! -L "${attempt_parent}" ] || {
  echo "run 8 refuses a symlink attempt parent: ${attempt_parent}" >&2
  exit 2
}
mkdir -p "${attempt_parent}"
attempt_parent="$(realpath -e -- "${attempt_parent}")"
case "${attempt_parent}" in
  "${RUN8_STORAGE_ROOT}"/*) ;;
  *) echo "run 8 attempt parent escaped the validated root: ${attempt_parent}" >&2; exit 2 ;;
esac
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs" \
  "${attempt_dir}/secrets" "${attempt_dir}/services" "${attempt_dir}/tmp"

adapter_token_file="${attempt_dir}/secrets/aar-autodata-adapter.token"
broker_token_file="${attempt_dir}/secrets/autodata-broker.token"
"${BROKER_PYTHON}" -c 'import secrets; print(secrets.token_urlsafe(48))' > "${adapter_token_file}"
"${BROKER_PYTHON}" -c 'import secrets; print(secrets.token_urlsafe(48))' > "${broker_token_file}"
chmod 600 "${adapter_token_file}" "${broker_token_file}"
require_mode_0600 adapter-token "${adapter_token_file}"
require_mode_0600 broker-token "${broker_token_file}"

budget_scope_id="run8-${attempt_id}"
resource_profile=run8-production-v1
profile_path="${attempt_dir}/metadata/autodata_resource_profile.json"
profile_digest="$("${REPO}/.venv/bin/python" - \
  "${profile_path}" "${AUTODATA_SHA}" "${resource_profile}" \
  "${budget_scope_id}" "${AUTODATA_MAX_COST_USD}" \
  "${AUTODATA_REQUIRED_RETAINED_ROWS}" \
  "${AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD}" \
  "${GENERATOR_INPUT_RATE}" "${GENERATOR_OUTPUT_RATE}" \
  "${JUDGE_INPUT_RATE}" "${JUDGE_OUTPUT_RATE}" <<'PY'
import hashlib, json, sys
from pathlib import Path

profile = {
    "schema": "aar.autodata.resource-profile/v1",
    "name": sys.argv[3],
    "autodata_framework_commit": sys.argv[2],
    "budget_scope_id": sys.argv[4],
    "max_cost_usd": sys.argv[5],
    "required_retained_rows": int(sys.argv[6]),
    "max_estimated_cost_per_task_usd": sys.argv[7],
    "max_concurrency": 4,
    "max_wall_seconds": 10800,
    "training_view": "sft",
    "generator": {
        "model": "Kimi-K2.6",
        "deployment_id": "winnieyangwn-kimi26",
        "url": "https://ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud/v1",
        "max_output_tokens": 1536,
        "input_usd_per_million": sys.argv[8],
        "output_usd_per_million": sys.argv[9],
    },
    "judge": {
        "model": "gpt-5-6-luna",
        "max_output_tokens": 512,
        "input_usd_per_million": sys.argv[10],
        "output_usd_per_million": sys.argv[11],
    },
    "executor": {
        "kind": "sandoq-firecracker",
        "environment": "oci-runner-firecracker-small",
        "image": "docker.io/library/python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f",
        "expected_image_id": "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316",
    },
}
payload = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
Path(sys.argv[1]).write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
print(hashlib.sha256(payload).hexdigest())
PY
)"

printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

for item in \
  "REPO:${REPO}" "ATTEMPT:${attempt_dir}" "BASELINE:${REUSED_BASELINE}" \
  "HARNESS_ENV:${HARNESS_ENV}" "AUTODATA_ROOT:${AUTODATA_ROOT}" \
  "BROKER_PYTHON:${BROKER_PYTHON}" "EXECSIDECAR_TOKEN_FILE:${EXECSIDECAR_TOKEN_FILE}" \
  "ADAPTER_TOKEN_FILE:${adapter_token_file}" "BROKER_TOKEN_FILE:${broker_token_file}" \
  "GENERATOR_URL:${GENERATOR_URL}" \
  "VLLM_WORKER_SH:${VLLM_WORKER_SH}" \
  "AUTODATA_MAX_COST_USD:${AUTODATA_MAX_COST_USD}" \
  "AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD:${AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD}" \
  "GENERATOR_INPUT_RATE:${GENERATOR_INPUT_RATE}" \
  "GENERATOR_OUTPUT_RATE:${GENERATOR_OUTPUT_RATE}" \
  "JUDGE_INPUT_RATE:${JUDGE_INPUT_RATE}" "JUDGE_OUTPUT_RATE:${JUDGE_OUTPUT_RATE}"; do
  safe_export_value "${item%%:*}" "${item#*:}"
done

job_id="$(sbatch --parsable \
  --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=16 --mem=128G --time=02:00:00 \
  --job-name=aar-gemma-vllm-run8-launch \
  --output="${attempt_dir}/logs/pipeline-%j.out" \
  --export=AAR_REPO="${REPO}",AAR_RUNTIME_ROOT="${attempt_dir}",AAR_RUN_ATTEMPT_DIR="${attempt_dir}",AAR_BASELINE_GIT_COMMIT="${commit}",AAR_REUSED_BASELINE="${REUSED_BASELINE}",HARNESS_ENV="${HARNESS_ENV}",LLM_UNCERTAINTY_SRC="${LLM_UNCERTAINTY_SRC}",LLM_UNCERTAINTY_SOURCE_MANIFEST="${LLM_UNCERTAINTY_SOURCE_MANIFEST}",AUTODATA_SOURCE_ROOT="${AUTODATA_ROOT}",AAR_RUN8_AUTODATA_SHA="${AUTODATA_SHA}",AAR_RUN8_BROKER_PYTHON="${BROKER_PYTHON}",AAR_RUN8_EXECSIDECAR_TOKEN_FILE="${EXECSIDECAR_TOKEN_FILE}",AAR_RUN8_ADAPTER_TOKEN_FILE="${adapter_token_file}",AAR_RUN8_BROKER_TOKEN_FILE="${broker_token_file}",AAR_RUN8_GENERATOR_URL="${GENERATOR_URL}",AAR_RUN8_VLLM_WORKER_SH="${VLLM_WORKER_SH}",AAR_RUN8_BUDGET_SCOPE_ID="${budget_scope_id}",AAR_RUN8_RESOURCE_PROFILE="${resource_profile}",AAR_RUN8_RESOURCE_PROFILE_SHA256="${profile_digest}",AAR_RUN8_AUTODATA_MAX_COST_USD="${AUTODATA_MAX_COST_USD}",AAR_RUN8_REQUIRED_RETAINED_ROWS="${AUTODATA_REQUIRED_RETAINED_ROWS}",AAR_RUN8_AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD="${AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD}",AAR_RUN8_GENERATOR_INPUT_USD_PER_MILLION="${GENERATOR_INPUT_RATE}",AAR_RUN8_GENERATOR_OUTPUT_USD_PER_MILLION="${GENERATOR_OUTPUT_RATE}",AAR_RUN8_JUDGE_INPUT_USD_PER_MILLION="${JUDGE_INPUT_RATE}",AAR_RUN8_JUDGE_OUTPUT_USD_PER_MILLION="${JUDGE_OUTPUT_RATE}",USER="${USER}" \
  "${SCRIPT_DIR}/run_8_pipeline.sbatch")"

printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nautodata_framework_commit=%s\nreused_baseline=%s\nresearch_chains=1\nmax_iterations_per_chain=2\nevaluator_jobs=1\nevaluator_gpus_per_job=4\nautodata_budget_scope_id=%s\nautodata_max_cost_usd=%s\nautodata_required_retained_rows=%s\ngenerator_deployment_id=winnieyangwn-kimi26\ngenerator_model=Kimi-K2.6\njudge_model=gpt-5-6-luna\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${AUTODATA_SHA}" "${REUSED_BASELINE}" \
  "${budget_scope_id}" "${AUTODATA_MAX_COST_USD}" "${AUTODATA_REQUIRED_RETAINED_ROWS}" | \
  tee "${attempt_dir}/metadata/submission.txt"
