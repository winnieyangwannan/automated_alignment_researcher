#!/bin/bash
#SBATCH --job-name=aar-run8-autodata-services
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=7-00:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_8.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing retained attempt}"
EXPECTED_COMMIT="${AAR_BASELINE_GIT_COMMIT:?missing submitted commit}"
AUTODATA_ROOT="${AUTODATA_SOURCE_ROOT:?missing canonical AutoData checkout}"
AUTODATA_SHA="${AAR_RUN8_AUTODATA_SHA:?missing canonical AutoData pin}"
BROKER_PYTHON="${AAR_RUN8_BROKER_PYTHON:?missing broker Python}"
EXECSIDECAR_TOKEN_FILE="${AAR_RUN8_EXECSIDECAR_TOKEN_FILE:?missing execsidecar token file}"
ADAPTER_TOKEN_FILE="${AAR_RUN8_ADAPTER_TOKEN_FILE:?missing adapter token file}"
BROKER_TOKEN_FILE="${AAR_RUN8_BROKER_TOKEN_FILE:?missing broker token file}"
ATTEMPT_DIR="$(realpath -e -- "${ATTEMPT_DIR}")"
case "${ATTEMPT_DIR}" in
  "/storage/home/${USER:?}/aar-runs/"*) ;;
  *) echo "Run 8 attempt escaped /storage/home/${USER}/aar-runs: ${ATTEMPT_DIR}" >&2; exit 2 ;;
esac
export TMPDIR="${ATTEMPT_DIR}/tmp"
mkdir -p "${TMPDIR}"

require_mode_0600() {
  local name="$1" path="$2"
  if [ ! -f "${path}" ] || [ -L "${path}" ]; then
    echo "${name} must be a regular non-symlink file" >&2
    exit 2
  fi
  if [ "$(stat -c '%a' -- "${path}")" != 600 ] || \
    [ "$(stat -c '%u' -- "${path}")" != "$(id -u)" ] || [ ! -s "${path}" ]; then
    echo "${name} must be nonempty, owner-only, and mode 0600" >&2
    exit 2
  fi
}

run_adapter_child() {
  # Load allowlisted values only inside the adapter process. The broker itself
  # receives no inherited model or agent key and reads workload secrets from the
  # independently validated mode-0600 file.
  export REPO AAR_REPO="${REPO}" HARNESS_ENV
  # shellcheck disable=SC1091
  source "${REPO}/scripts/aar_runtime_env.sh"
  [ -n "${MODEL_API_KEY:-}" ] || { echo "AutoData adapter requires MODEL_API_KEY" >&2; exit 2; }
  unset HF_TOKEN HUGGING_FACE_HUB_TOKEN ANTHROPIC_API_KEY ANT_high_prio_API ANT_API_KEY
  unset OAI_API OPENAI_API_KEY LLAMA_API_KEY

  export AUTODATA_SOURCE_ROOT="${AUTODATA_ROOT}"
  export AAR_AUTODATA_TOKEN
  AAR_AUTODATA_TOKEN="$(<"${ADAPTER_TOKEN_FILE}")"
  export AUTODATA_BROKER_AUTH_TOKEN
  AUTODATA_BROKER_AUTH_TOKEN="$(<"${BROKER_TOKEN_FILE}")"
  export AAR_AUTODATA_BROKER_AUTH_SECRET_REF=AUTODATA_BROKER_AUTH_TOKEN
  export AAR_AUTODATA_BROKER_URL
  export AAR_AUTODATA_GENERATOR_MODEL=Kimi-K2.6
  export AAR_AUTODATA_GENERATOR_DEPLOYMENT_ID=winnieyangwn-kimi26
  export AAR_AUTODATA_GENERATOR_URL="${AAR_RUN8_GENERATOR_URL:?missing resolved Kimi route}"
  export AAR_AUTODATA_GENERATOR_TOKEN_ENV=MODEL_API_KEY
  export AAR_AUTODATA_GENERATOR_MAX_TOKENS=1536
  export AAR_AUTODATA_GENERATOR_TIMEOUT=90
  export AAR_AUTODATA_GENERATOR_INPUT_USD_PER_MILLION="${AAR_RUN8_GENERATOR_INPUT_USD_PER_MILLION:?missing Kimi input rate}"
  export AAR_AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION="${AAR_RUN8_GENERATOR_OUTPUT_USD_PER_MILLION:?missing Kimi output rate}"
  export AAR_AUTODATA_JUDGE_MODEL=gpt-5-6-luna
  export AAR_AUTODATA_JUDGE_URL=https://api.meta.ai/v1/responses
  export AAR_AUTODATA_JUDGE_TOKEN_ENV=MODEL_API_KEY
  export AAR_AUTODATA_JUDGE_MAX_TOKENS=512
  export AAR_AUTODATA_JUDGE_TIMEOUT=90
  export AAR_AUTODATA_JUDGE_INPUT_USD_PER_MILLION="${AAR_RUN8_JUDGE_INPUT_USD_PER_MILLION:?missing Luna input rate}"
  export AAR_AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION="${AAR_RUN8_JUDGE_OUTPUT_USD_PER_MILLION:?missing Luna output rate}"
  export AAR_AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD="${AAR_RUN8_AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD:?missing per-task cost bound}"
  export AAR_AUTODATA_MAX_CONCURRENCY=4
  export AAR_AUTODATA_MAX_WALL_SECONDS=10800
  export AAR_AUTODATA_SANDOQ_ENVIRONMENT=oci-runner-firecracker-small
  export AAR_AUTODATA_OCI_IMAGE=docker.io/library/python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
  export AAR_AUTODATA_OCI_EXPECTED_IMAGE_ID=df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316
  export AAR_AUTODATA_TASK_CPUS=2
  export AAR_AUTODATA_TASK_MEMORY_MB=2048
  export AAR_AUTODATA_RECIPE_ROOT="${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing"
  export AAR_AUTODATA_REQUIRED_CONTROLS_JSON
  AAR_AUTODATA_REQUIRED_CONTROLS_JSON="$("${BROKER_PYTHON}" - \
    "${AAR_RUN8_RESOURCE_PROFILE:?missing resource profile}" \
    "${AAR_RUN8_RESOURCE_PROFILE_SHA256:?missing resource profile digest}" \
    "${AAR_RUN8_BUDGET_SCOPE_ID:?missing budget scope}" \
    "${AAR_RUN8_AUTODATA_MAX_COST_USD:?missing campaign cap}" \
    "${AAR_RUN8_REQUIRED_RETAINED_ROWS:?missing retained rows}" <<'PY'
import json, sys
print(json.dumps({
    "resource_profile": sys.argv[1],
    "resource_profile_sha256": sys.argv[2],
    "budget_scope_id": sys.argv[3],
    "max_cost_usd": sys.argv[4],
    "required_retained_rows": int(sys.argv[5]),
}, sort_keys=True, separators=(",", ":")))
PY
)"
  export AAR_AUTODATA_REQUIRED_SPEC_JSON
  AAR_AUTODATA_REQUIRED_SPEC_JSON="$("${BROKER_PYTHON}" - \
    "${AAR_RUN8_RESOURCE_PROFILE}" <<'PY'
import json, sys
print(json.dumps({
    "schema": "aar.autodata.request/v1",
    "resource_profile": sys.argv[1],
    "safety_axis": "honesty_sycophancy_concealing_uncertainty",
    "training_view": "sft",
}, sort_keys=True, separators=(",", ":")))
PY
)"
  export PYTHONPATH="${REPO}:${AUTODATA_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

  exec "${BROKER_PYTHON}" -u "${REPO}/scripts/autodata_service.py" \
    --checkout "${AUTODATA_ROOT}" \
    --state-root "${ATTEMPT_DIR}/services/adapter-state" \
    --pipeline-sha "${AUTODATA_SHA}" \
    --recipe-root "${AAR_AUTODATA_RECIPE_ROOT}" \
    --row-transform native \
    --host 0.0.0.0 \
    --port "${adapter_port}" \
    --driver-script "${REPO}/scripts/autodata_live_sandoq_driver.py" \
    --backend live
}

if [ "${1:-}" = --adapter-child ]; then
  run_adapter_child
  exit
fi

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "wrong AAR branch" >&2; exit 2; }
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || { echo "AAR commit drift" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked AAR worktree is dirty" >&2
  exit 2
fi
[ "$(git -C "${AUTODATA_ROOT}" branch --show-current)" = main ] || { echo "wrong AutoData branch" >&2; exit 2; }
[ "$(git -C "${AUTODATA_ROOT}" rev-parse HEAD)" = "${AUTODATA_SHA}" ] || { echo "AutoData commit drift" >&2; exit 2; }
[ -z "$(git -C "${AUTODATA_ROOT}" status --porcelain --untracked-files=all)" ] || {
  echo "canonical AutoData checkout is dirty" >&2
  exit 2
}
[ -x "${BROKER_PYTHON}" ] || { echo "broker Python is not executable" >&2; exit 2; }
PYTHONPATH="${AUTODATA_ROOT}/src" "${BROKER_PYTHON}" -c \
  'import aiohttp, autodata, sandoq_client'
require_mode_0600 HARNESS_ENV "${HARNESS_ENV}"
require_mode_0600 execsidecar-token "${EXECSIDECAR_TOKEN_FILE}"
require_mode_0600 adapter-token "${ADAPTER_TOKEN_FILE}"
require_mode_0600 broker-token "${BROKER_TOKEN_FILE}"

read -r broker_port adapter_port < <("${BROKER_PYTHON}" -c '
import socket
sockets = [socket.socket() for _ in range(2)]
for sock in sockets:
    sock.bind(("", 0))
print(*(sock.getsockname()[1] for sock in sockets))
')
if [ -z "${broker_port}" ] || [ -z "${adapter_port}" ] || [ "${broker_port}" = "${adapter_port}" ]; then
  echo "failed to reserve distinct service ports" >&2
  exit 2
fi
service_host="$(hostname -f)"
export AAR_AUTODATA_BROKER_URL="http://${service_host}:${broker_port}"
export adapter_port

broker_pid=""
adapter_pid=""
cleanup() {
  trap - EXIT TERM INT HUP
  for pid in "${adapter_pid}" "${broker_pid}"; do
    [ -n "${pid}" ] || continue
    kill -TERM -- "-${pid}" 2>/dev/null || true
  done
  for _ in $(seq 1 30); do
    alive=0
    for pid in "${adapter_pid}" "${broker_pid}"; do
      [ -z "${pid}" ] || ! kill -0 -- "-${pid}" 2>/dev/null || alive=1
    done
    [ "${alive}" = 1 ] || break
    sleep 1
  done
  for pid in "${adapter_pid}" "${broker_pid}"; do
    [ -n "${pid}" ] || continue
    kill -KILL -- "-${pid}" 2>/dev/null || true
    wait "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT TERM INT HUP

setsid env \
  PYTHONPATH="${AUTODATA_ROOT}/src" \
  "${BROKER_PYTHON}" -u -m autodata.broker.cli serve \
  --root "${ATTEMPT_DIR}/services/broker-state" \
  --gateway-url https://sandoq-gateway.eks-prod.cf.aws.metafb.cloud \
  --host 0.0.0.0 \
  --port "${broker_port}" \
  --max-concurrent 4 \
  --execsidecar-token-file "${EXECSIDECAR_TOKEN_FILE}" \
  --auth-token-file "${BROKER_TOKEN_FILE}" \
  --workload-env-file "${HARNESS_ENV}" \
  --anonymous-registry docker.io \
  > "${ATTEMPT_DIR}/logs/autodata-broker-${SLURM_JOB_ID}.log" 2>&1 &
broker_pid=$!

check_http() {
  "${BROKER_PYTHON}" - "$1" "$2" "$3" <<'PY'
import json, sys, urllib.request
token = open(sys.argv[2], encoding="utf-8").read().strip()
request = urllib.request.Request(sys.argv[1], headers={"Authorization": "Bearer " + token})
with urllib.request.urlopen(request, timeout=5) as response:
    value = json.load(response)
if sys.argv[3] == "broker" and value.get("ready") is not True:
    raise SystemExit(1)
if sys.argv[3] == "adapter" and value.get("pipeline_sha") is None:
    raise SystemExit(1)
PY
}

broker_ready=0
for _ in $(seq 1 180); do
  if check_http "${AAR_AUTODATA_BROKER_URL}/readyz" "${BROKER_TOKEN_FILE}" broker 2>/dev/null; then
    broker_ready=1
    break
  fi
  kill -0 -- "-${broker_pid}" 2>/dev/null || {
    echo "canonical AutoData broker exited during startup" >&2
    exit 1
  }
  sleep 2
done
[ "${broker_ready}" = 1 ] || { echo "canonical AutoData broker did not become ready" >&2; exit 1; }

# Exercise the actual canonical broker, SandoQ Firecracker lease, pinned image,
# and authorized runner token before exposing the adapter to the AAR chain.
PYTHONPATH="${AUTODATA_ROOT}/src" "${BROKER_PYTHON}" \
  "${REPO}/scripts/autodata_native_broker_canary.py" \
  --broker-url "${AAR_AUTODATA_BROKER_URL}" \
  --broker-auth-token-file "${BROKER_TOKEN_FILE}" \
  --output "${ATTEMPT_DIR}/metadata/native_broker_canary.json" \
  --timeout-seconds 900

# Exercise qualified Kimi generation and Luna judging from the Firecracker
# workload before the live adapter can accept an AAR request. The report keeps
# only safe usage/provenance; generated content remains temporary.
PYTHONPATH="${AUTODATA_ROOT}/src" "${BROKER_PYTHON}" \
  "${REPO}/scripts/autodata_model_broker_canary.py" \
  --broker-url "${AAR_AUTODATA_BROKER_URL}" \
  --broker-auth-token-file "${BROKER_TOKEN_FILE}" \
  --recipe-root "${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing" \
  --generator-url "${AAR_RUN8_GENERATOR_URL}" \
  --generator-input-usd-per-million "${AAR_RUN8_GENERATOR_INPUT_USD_PER_MILLION}" \
  --generator-output-usd-per-million "${AAR_RUN8_GENERATOR_OUTPUT_USD_PER_MILLION}" \
  --judge-input-usd-per-million "${AAR_RUN8_JUDGE_INPUT_USD_PER_MILLION}" \
  --judge-output-usd-per-million "${AAR_RUN8_JUDGE_OUTPUT_USD_PER_MILLION}" \
  --timeout-seconds 900 \
  --output "${ATTEMPT_DIR}/metadata/model_broker_canary.json"

# Re-enter this committed script in a new process group. The child reads the
# secret files itself, so neither token value appears in argv or Slurm export.
setsid bash "$0" --adapter-child \
  > "${ATTEMPT_DIR}/logs/aar-autodata-adapter-${SLURM_JOB_ID}.log" 2>&1 &
adapter_pid=$!

adapter_url="http://${service_host}:${adapter_port}"
adapter_ready=0
for _ in $(seq 1 180); do
  if check_http "${adapter_url}/health" "${ADAPTER_TOKEN_FILE}" adapter 2>/dev/null; then
    adapter_ready=1
    break
  fi
  kill -0 -- "-${adapter_pid}" 2>/dev/null || {
    echo "live AAR AutoData adapter exited during startup" >&2
    exit 1
  }
  sleep 2
done
[ "${adapter_ready}" = 1 ] || { echo "live AAR AutoData adapter did not become ready" >&2; exit 1; }

services_tmp="$(mktemp "${ATTEMPT_DIR}/metadata/.autodata_services.env.XXXXXX")"
{
  printf 'export AAR_RUN8_SERVICES_JOB_ID=%q\n' "${SLURM_JOB_ID}"
  printf 'export AAR_AUTODATA_URL=%q\n' "${adapter_url}"
  printf 'export AAR_AUTODATA_BROKER_URL=%q\n' "${AAR_AUTODATA_BROKER_URL}"
  printf 'export AAR_AUTODATA_TOKEN_FILE=%q\n' "${ADAPTER_TOKEN_FILE}"
  printf 'export AAR_AUTODATA_SHA=%q\n' "${AUTODATA_SHA}"
  printf 'export AAR_AUTODATA_GENERATOR_DEPLOYMENT_ID=%q\n' winnieyangwn-kimi26
  printf 'export AAR_AUTODATA_GENERATOR_MODEL=%q\n' Kimi-K2.6
  printf 'export AAR_AUTODATA_JUDGE_MODEL=%q\n' gpt-5-6-luna
} > "${services_tmp}"
chmod 600 "${services_tmp}"
mv -- "${services_tmp}" "${ATTEMPT_DIR}/metadata/autodata_services.env"
echo "[run8-services] canonical broker and live adapter ready on ${service_host}"

children="${ATTEMPT_DIR}/metadata/children.env"
while [ ! -s "${children}" ]; do
  kill -0 -- "-${broker_pid}" 2>/dev/null || { echo "AutoData broker stopped" >&2; exit 1; }
  kill -0 -- "-${adapter_pid}" 2>/dev/null || { echo "AutoData adapter stopped" >&2; exit 1; }
  if [ -z "$(squeue -h -j "${AAR_RUN8_LAUNCH_JOB_ID:?missing launch job id}" -o '%T')" ]; then
    echo "Run 8 launcher ended without publishing child job IDs" >&2
    exit 1
  fi
  sleep 5
done
chain_id="$(awk -F= '$1 == "research_chain_job" {print $2}' "${children}")"
case "${chain_id}" in ''|*[!0-9]*) echo "invalid Run 8 research-chain job ID" >&2; exit 2;; esac

while [ -n "$(squeue -h -j "${chain_id}" -o '%T')" ]; do
  kill -0 -- "-${broker_pid}" 2>/dev/null || { echo "AutoData broker stopped" >&2; exit 1; }
  kill -0 -- "-${adapter_pid}" 2>/dev/null || { echo "AutoData adapter stopped" >&2; exit 1; }
  sleep 10
done
printf 'services_job_id=%s\nresearch_chain_job=%s\nstopped_at_utc=%s\n' \
  "${SLURM_JOB_ID}" "${chain_id}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > "${ATTEMPT_DIR}/metadata/autodata_services_stopped.txt"
echo "[run8-services] research chain ended; stopping broker and adapter"
