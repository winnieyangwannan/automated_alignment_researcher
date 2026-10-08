#!/bin/bash
#SBATCH --job-name=aar-run9-firecracker-canary
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_9_capacity_canary.sh}"
AUTODATA="${AAR_AUTODATA_CHECKOUT:?missing AutoData checkout}"
ROOT="${AAR_RUN9_CANARY_ROOT:?missing retained canary root}"
ENVIRONMENT="${AAR_AUTODATA_ENVIRONMENT:?missing Firecracker environment}"
CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:?missing canary concurrency}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:?missing broker Python}"
CAPABILITY_FILE="${AAR_AUTODATA_CAPABILITY_FILE:?missing capability file}"

port=$(( 10000 + (${SLURM_JOB_ID:?} % 40000) ))
broker_url="http://127.0.0.1:${port}"
broker_pid=""
cleanup() {
  if [ -n "${broker_pid}" ]; then
    kill "${broker_pid}" 2>/dev/null || true
    wait "${broker_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

mkdir -p "${ROOT}/broker" "${ROOT}/reports"
PYTHONPATH="${AUTODATA}/src" "${BROKER_PYTHON}" -m autodata.broker.cli \
  --root "${ROOT}/broker" \
  --gateway-url "${SANDOQ_GATEWAY_URL:-https://sandoq-gateway.eks-prod.cf.aws.metafb.cloud}" \
  --host 127.0.0.1 --port "${port}" \
  --max-concurrent "${CONCURRENCY}" \
  --auth-token-file "${CAPABILITY_FILE}" \
  --execsidecar-token-file "${AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE:?}" \
  --workload-env-file "${AAR_AUTODATA_MODEL_ENV_FILE:?}" \
  --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY:?}" \
  --anonymous-registry docker.io --no-registry-preflight \
  > "${ROOT}/broker.log" 2>&1 &
broker_pid=$!

ready=0
for probe in $(seq 1 60); do
  if PYTHONPATH="${AUTODATA}/src" "${BROKER_PYTHON}" -c \
    'import pathlib,sys,urllib.request; token=pathlib.Path(sys.argv[1]).read_text().strip(); request=urllib.request.Request(sys.argv[2]+"/healthz",headers={"Authorization":"Bearer "+token}); urllib.request.urlopen(request,timeout=2).read()' \
    "${CAPABILITY_FILE}" "${broker_url}" 2>/dev/null; then
    ready=1
    break
  fi
  kill -0 "${broker_pid}" 2>/dev/null || { echo "broker exited during startup" >&2; exit 2; }
  sleep 1
done
kill -0 "${broker_pid}" 2>/dev/null || { echo "broker is not running" >&2; exit 2; }
[ "${ready}" = 1 ] || { echo "broker health probe timed out" >&2; exit 2; }

pids=()
for index in 1 2 3 4; do
  PYTHONPATH="${AUTODATA}/src:${REPO}" "${REPO}/.venv/bin/python" \
    "${REPO}/scripts/autodata_model_broker_canary.py" \
    --broker-url "${broker_url}" \
    --broker-auth-token-file "${CAPABILITY_FILE}" \
    --recipe-root "${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing" \
    --output "${ROOT}/reports/canary-${index}.json" \
    --environment "${ENVIRONMENT}" \
    --generator-max-output-tokens 768 \
    --model-request-max-attempts 1 \
    --timeout-seconds 1800 \
    > "${ROOT}/canary-${index}.log" 2>&1 &
  pids+=("$!")
done

failed=0
for pid in "${pids[@]}"; do
  if ! wait "${pid}"; then
    failed=1
  fi
done
[ "${failed}" = 0 ] || { echo "one or more model-backed canaries failed" >&2; exit 1; }

PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" - "${ROOT}" "${ENVIRONMENT}" "${CONCURRENCY}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
environment = sys.argv[2]
concurrency = int(sys.argv[3])
reports = [json.loads(path.read_text()) for path in sorted((root / "reports").glob("canary-*.json"))]
if len(reports) != 4 or any(not report.get("success") for report in reports):
    raise SystemExit("capacity canary did not retain four successful reports")
if any(report.get("environment") != environment for report in reports):
    raise SystemExit("capacity canary used the wrong Firecracker environment")
summary = {
    "schema": "aar.autodata.firecracker-capacity-canary/v1",
    "success": True,
    "environment": environment,
    "concurrency": concurrency,
    "broker_job_ids": [report["broker_job_id"] for report in reports],
    "sandoq_session_ids": [report["sandoq_session_id"] for report in reports],
}
(root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY
chmod 600 "${ROOT}/summary.json"
echo "Run 9 Firecracker capacity canary passed: ${ROOT}/summary.json"
