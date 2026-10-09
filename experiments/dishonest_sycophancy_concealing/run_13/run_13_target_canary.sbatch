#!/bin/bash
#SBATCH --job-name=aar-run13-target-canary
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:15:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_13.sh}"
AUTODATA="${AAR_AUTODATA_CHECKOUT:?missing AutoData checkout}"
ROOT="${AAR_RUN13_ROOT:?missing attempt root}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:?missing broker Python}"
CAPABILITY_FILE="${AAR_AUTODATA_CAPABILITY_FILE:?missing capability file}"
BINDING="${AAR_RUN13_TARGET_BINDING:?missing target binding}"
CANARY_PYTHONPATH="${AUTODATA}/src:${REPO}"

PYTHONPATH="${CANARY_PYTHONPATH}" "${REPO}/.venv/bin/python" -c \
  'from autodata.broker.archive import build_archive, extract_archive; from autodata.broker.client import BrokerClient; from autodata.broker.models import BrokerJobSpec'

port=$((10000 + (${SLURM_JOB_ID:?} % 40000)))
broker_url="http://127.0.0.1:${port}"
database_root="${SLURM_TMPDIR:-/tmp}/aar-run13-broker-${SLURM_JOB_ID}"
database="${database_root}/broker.db"
broker_pid=""

cleanup() {
  if [ -n "${broker_pid}" ]; then
    kill "${broker_pid}" 2>/dev/null || true
    wait "${broker_pid}" 2>/dev/null || true
  fi
  if [ -f "${database}" ]; then
    cp -- "${database}" "${ROOT}/broker.db"
    chmod 600 "${ROOT}/broker.db"
  fi
}
trap cleanup EXIT INT TERM

mkdir -p "${database_root}" "${ROOT}/broker"
chmod 700 "${database_root}" "${ROOT}/broker"
broker_args=(
  --runner local-bwrap
  --root "${ROOT}/broker"
  --database "${database}"
  --host 127.0.0.1 --port "${port}"
  --max-concurrent 1
  --auth-token-file "${CAPABILITY_FILE}"
  --workload-env-file "${AAR_AUTODATA_MODEL_ENV_FILE:?}"
  --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY:?}"
  --anonymous-registry docker.io
)
PYTHONPATH="${AUTODATA}/src" "${BROKER_PYTHON}" -m autodata.broker.cli \
  "${broker_args[@]}" > "${ROOT}/broker.log" 2>&1 &
broker_pid=$!

ready=0
for probe in $(seq 1 60); do
  if "${BROKER_PYTHON}" -c \
    'import pathlib,sys,urllib.request; token=pathlib.Path(sys.argv[1]).read_text().strip(); request=urllib.request.Request(sys.argv[2]+"/healthz",headers={"Authorization":"Bearer "+token}); urllib.request.urlopen(request,timeout=2).read()' \
    "${CAPABILITY_FILE}" "${broker_url}" 2>/dev/null; then
    ready=1
    break
  fi
  kill -0 "${broker_pid}" 2>/dev/null || { echo "broker exited during startup" >&2; exit 2; }
  sleep 1
done
[ "${ready}" = 1 ] || { echo "broker health probe timed out" >&2; exit 2; }

start_ns="$(date +%s%N)"
PYTHONPATH="${CANARY_PYTHONPATH}" "${REPO}/.venv/bin/python" \
  "${REPO}/scripts/autodata_model_broker_canary.py" \
  --broker-url "${broker_url}" \
  --broker-auth-token-file "${CAPABILITY_FILE}" \
  --recipe-root "${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing" \
  --target-binding "${BINDING}" \
  --output "${ROOT}/canary-report.json" \
  --environment oci-runner-firecracker-large \
  --generator-url "${AAR_RUN13_GENERATOR_URL:?}" \
  --generator-host-header "${AAR_RUN13_GENERATOR_HOST_HEADER:?}" \
  --generator-deployment-id "${AAR_RUN13_GENERATOR_DEPLOYMENT_ID:?}" \
  --generator-max-input-tokens 196608 \
  --generator-max-output-tokens 65536 \
  --judge-max-input-tokens 1000000 \
  --judge-max-output-tokens 65536 \
  --target-max-input-tokens 196608 \
  --target-max-output-tokens 65536 \
  --target-canary-id-prefix run13-adapter-target-canary \
  --model-request-max-attempts 1 \
  --timeout-seconds 600 \
  > "${ROOT}/canary.log" 2>&1
end_ns="$(date +%s%N)"

PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" - "${ROOT}" "${start_ns}" "${end_ns}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
report = json.loads((root / "canary-report.json").read_text())
if not report.get("success") or report.get("provider_call_count") != 3:
    raise SystemExit("target-aware canary did not record three provider calls")
if [call.get("role") for call in report["provider_usage"]] != [
    "generator", "target", "judge"
]:
    raise SystemExit("target-aware canary provider order is invalid")
timing = {
    "schema": "aar.autodata.adapter-target-timing/v1",
    "elapsed_seconds": round((int(sys.argv[3]) - int(sys.argv[2])) / 1e9, 3),
}
(root / "timing.json").write_text(json.dumps(timing, indent=2, sort_keys=True) + "\n")
print(json.dumps({"success": True, **timing}, sort_keys=True))
PY

echo "Run 13 target-aware task passed: ${ROOT}/canary-report.json"
