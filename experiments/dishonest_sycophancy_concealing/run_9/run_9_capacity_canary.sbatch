#!/bin/bash
#SBATCH --job-name=aar-run9-broker-canary
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
RUNNER="${AAR_AUTODATA_BROKER_RUNNER:?missing broker runner}"
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
broker_args=(
  --runner "${RUNNER}"
  --root "${ROOT}/broker"
  --host 127.0.0.1 --port "${port}"
  --max-concurrent "${CONCURRENCY}"
  --auth-token-file "${CAPABILITY_FILE}"
  --workload-env-file "${AAR_AUTODATA_MODEL_ENV_FILE:?}"
  --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY:?}"
  --anonymous-registry docker.io
)
if [ "${RUNNER}" = sandoq-firecracker ]; then
  broker_args+=(
    --gateway-url "${SANDOQ_GATEWAY_URL:-https://sandoq-gateway.eks-prod.cf.aws.metafb.cloud}"
    --execsidecar-token-file "${AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE:?}"
    --no-registry-preflight
  )
elif [ "${RUNNER}" != local-bwrap ]; then
  echo "unsupported broker runner: ${RUNNER}" >&2
  exit 2
fi
PYTHONPATH="${AUTODATA}/src" "${BROKER_PYTHON}" -m autodata.broker.cli \
  "${broker_args[@]}" \
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
for index in $(seq 1 "${CONCURRENCY}"); do
  PYTHONPATH="${AUTODATA}/src:${REPO}" "${REPO}/.venv/bin/python" \
    "${REPO}/scripts/autodata_model_broker_canary.py" \
    --broker-url "${broker_url}" \
    --broker-auth-token-file "${CAPABILITY_FILE}" \
    --recipe-root "${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing" \
    --output "${ROOT}/reports/canary-${index}.json" \
    --environment "${ENVIRONMENT}" \
    --generator-url "${AAR_AUTODATA_GENERATOR_URL:?}" \
    --generator-host-header "${AAR_AUTODATA_GENERATOR_HOST_HEADER:?}" \
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

PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" - "${ROOT}" "${RUNNER}" "${ENVIRONMENT}" "${CONCURRENCY}" "${failed}" <<'PY'
import json
import pathlib
import sqlite3
import sys

root = pathlib.Path(sys.argv[1])
runner = sys.argv[2]
environment = sys.argv[3]
concurrency = int(sys.argv[4])
client_failure_count = int(sys.argv[5])
reports = [json.loads(path.read_text()) for path in sorted((root / "reports").glob("canary-*.json"))]
if any(report.get("environment") != environment for report in reports):
    raise SystemExit("capacity canary used the wrong Firecracker environment")
connection = sqlite3.connect(f"file:{root / 'broker' / 'broker.db'}?mode=ro", uri=True)
try:
    rows = connection.execute(
        "select id,status,sessionId,solveExitCode,specJson from jobs order by createdAt"
    ).fetchall()
finally:
    connection.close()
if len(rows) != concurrency:
    raise SystemExit("capacity canary did not create the requested broker jobs")
jobs = []
for job_id, status, session_id, solve_exit_code, spec_json in rows:
    spec = json.loads(spec_json)
    if spec.get("environment") != environment:
        raise SystemExit("capacity canary broker job used the wrong environment")
    jobs.append(
        {
            "broker_job_id": job_id,
            "status": status,
            "runner_session_id": session_id,
            "solve_exit_code": solve_exit_code,
        }
    )
if any(
    job["status"] != "SUCCEEDED"
    or not job["runner_session_id"]
    or job["solve_exit_code"] != 0
    for job in jobs
):
    raise SystemExit("capacity canary did not complete all broker jobs")
summary = {
    "schema": "aar.autodata.broker-capacity-canary/v2",
    "success": True,
    "runner": runner,
    "environment": environment,
    "concurrency": concurrency,
    "broker_job_ids": [job["broker_job_id"] for job in jobs],
    "runner_session_ids": [job["runner_session_id"] for job in jobs],
    "audited_sample_count": len(reports),
    "client_failure_count": client_failure_count,
}
(root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY
chmod 600 "${ROOT}/summary.json"
echo "Run 9 broker capacity canary passed: ${ROOT}/summary.json"
