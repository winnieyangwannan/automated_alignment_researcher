#!/bin/bash
#SBATCH --job-name=aar-run9-broker-canary
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=01:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_9_capacity_canary.sh}"
AUTODATA="${AAR_AUTODATA_CHECKOUT:?missing AutoData checkout}"
ROOT="${AAR_RUN9_CANARY_ROOT:?missing retained canary root}"
ENVIRONMENT="${AAR_AUTODATA_ENVIRONMENT:?missing Firecracker environment}"
CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:?missing canary concurrency}"
TASK_COUNT="${AAR_AUTODATA_CANARY_TASK_COUNT:?missing canary task count}"
RUNNER="${AAR_AUTODATA_BROKER_RUNNER:?missing broker runner}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:?missing broker Python}"
CAPABILITY_FILE="${AAR_AUTODATA_CAPABILITY_FILE:?missing capability file}"
KIMI_PROXY_INFO="${AAR_KIMI_PROXY_INFO:?missing Kimi proxy contract}"

port=$(( 10000 + (${SLURM_JOB_ID:?} % 40000) ))
broker_url="http://127.0.0.1:${port}"
bridge_port=$(( 50000 + (${SLURM_JOB_ID} % 15000) ))
generator_url="http://127.0.0.1:${bridge_port}/v1"
broker_pid=""
bridge_pid=""
broker_database_root="${SLURM_TMPDIR:-/tmp}/aar-run9-canary-broker-${SLURM_JOB_ID}"
broker_database="${broker_database_root}/broker.db"
retained_broker_database="${ROOT}/broker/broker.db"
snapshot_broker_database() {
  if [ -f "${broker_database}" ]; then
    "${BROKER_PYTHON}" -c \
      'import sqlite3,sys; connection=sqlite3.connect(sys.argv[1]); connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall(); connection.close()' \
      "${broker_database}"
    staging="${retained_broker_database}.tmp.$$"
    cp -- "${broker_database}" "${staging}"
    chmod 600 "${staging}"
    mv -- "${staging}" "${retained_broker_database}"
  fi
}
cleanup() {
  if [ -n "${broker_pid}" ]; then
    kill "${broker_pid}" 2>/dev/null || true
    wait "${broker_pid}" 2>/dev/null || true
  fi
  snapshot_broker_database || true
  if [ -n "${bridge_pid}" ]; then
    kill "${bridge_pid}" 2>/dev/null || true
    wait "${bridge_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

mkdir -p "${ROOT}/broker" "${ROOT}/reports" "${broker_database_root}"
chmod 700 "${broker_database_root}"
runtime_policy="${ROOT}/policy.runtime.json"
"${REPO}/.venv/bin/python" - "${AAR_AUTODATA_CAMPAIGN_POLICY:?}" "${runtime_policy}" "${generator_url}" <<'PY'
import json
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
policy = json.loads(source.read_text(encoding="utf-8"))
environment = policy["required_solve_env"]
environment["AUTODATA_GENERATOR_URL"] = sys.argv[3]
environment.pop("AUTODATA_GENERATOR_HOST_HEADER", None)
destination.write_text(
    json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
destination.chmod(0o600)
PY
"${REPO}/.venv/bin/python" "${REPO}/scripts/loopback_model_auth_bridge.py" \
  --proxy-info "${KIMI_PROXY_INFO}" --port "${bridge_port}" \
  >"${ROOT}/kimi-auth-bridge.log" 2>&1 &
bridge_pid=$!
for probe in $(seq 1 30); do
  if "${REPO}/.venv/bin/python" -c 'import sys,urllib.request; urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/healthz",timeout=2).read()' "${bridge_port}" 2>/dev/null; then
    break
  fi
  kill -0 "${bridge_pid}" 2>/dev/null || {
    echo "Kimi bridge exited during startup" >&2
    exit 2
  }
  sleep 1
done
kill -0 "${bridge_pid}" 2>/dev/null || { echo "Kimi bridge is not running" >&2; exit 2; }
broker_args=(
  --runner "${RUNNER}"
  --root "${ROOT}/broker"
  --database "${broker_database}"
  --host 127.0.0.1 --port "${port}"
  --max-concurrent "${CONCURRENCY}"
  --auth-token-file "${CAPABILITY_FILE}"
  --workload-env-file "${AAR_AUTODATA_MODEL_ENV_FILE:?}"
  --campaign-policy "${runtime_policy}"
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
load_started_ns="$(date +%s%N)"
for index in $(seq 1 "${TASK_COUNT}"); do
  PYTHONPATH="${AUTODATA}/src:${REPO}" "${REPO}/.venv/bin/python" \
    "${REPO}/scripts/autodata_model_broker_canary.py" \
    --broker-url "${broker_url}" \
    --broker-auth-token-file "${CAPABILITY_FILE}" \
    --recipe-root "${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing" \
    --output "${ROOT}/reports/canary-${index}.json" \
    --environment "${ENVIRONMENT}" \
    --generator-url "${generator_url}" \
    --generator-host-header "" \
    --generator-max-output-tokens 768 \
    --model-request-max-attempts 1 \
    --allow-judge-rejection \
    --timeout-seconds 1800 \
    > "${ROOT}/canary-${index}.log" 2>&1 &
  pids+=("$!")
done

failed=0
for pid in "${pids[@]}"; do
  if ! wait "${pid}"; then
    failed=$((failed + 1))
  fi
done
load_finished_ns="$(date +%s%N)"

PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" - \
  "${ROOT}" "${RUNNER}" "${ENVIRONMENT}" "${CONCURRENCY}" "${TASK_COUNT}" "${failed}" \
  "${broker_database}" "${load_started_ns}" "${load_finished_ns}" <<'PY'
import json
import pathlib
import sqlite3
import sys

root = pathlib.Path(sys.argv[1])
runner = sys.argv[2]
environment = sys.argv[3]
concurrency = int(sys.argv[4])
task_count = int(sys.argv[5])
client_failure_count = int(sys.argv[6])
broker_database = pathlib.Path(sys.argv[7])
elapsed_seconds = (int(sys.argv[9]) - int(sys.argv[8])) / 1_000_000_000
reports = [json.loads(path.read_text()) for path in sorted((root / "reports").glob("canary-*.json"))]
if any(report.get("environment") != environment for report in reports):
    raise SystemExit("capacity canary used the wrong Firecracker environment")
connection = sqlite3.connect(f"file:{broker_database}?mode=ro", uri=True)
try:
    rows = connection.execute(
        "select id,status,sessionId,solveExitCode,specJson from jobs order by createdAt"
    ).fetchall()
finally:
    connection.close()
if len(rows) != task_count:
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
    "success": client_failure_count == 0 and len(reports) == task_count,
    "runner": runner,
    "environment": environment,
    "concurrency": concurrency,
    "task_count": task_count,
    "broker_job_ids": [job["broker_job_id"] for job in jobs],
    "runner_session_ids": [job["runner_session_id"] for job in jobs],
    "audited_sample_count": len(reports),
    "client_failure_count": client_failure_count,
    "elapsed_seconds": elapsed_seconds,
    "completed_tasks_per_minute": task_count * 60 / elapsed_seconds,
    "accepted_row_count": sum(report.get("accepted_row_count", 0) for report in reports),
    "task_result_succeeded_count": sum(
        report.get("task_result_outcome") == "succeeded" for report in reports
    ),
    "task_result_failed_count": sum(
        report.get("task_result_outcome") == "failed" for report in reports
    ),
    "judge_call_count": sum(
        any(call.get("role") == "judge" for call in report.get("provider_usage", []))
        for report in reports
    ),
}
summary["accepted_rows_per_minute"] = (
    summary["accepted_row_count"] * 60 / elapsed_seconds
)
(root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
if not summary["success"]:
    raise SystemExit("capacity canary client validation was incomplete")
PY
chmod 600 "${ROOT}/summary.json"
echo "Run 9 broker capacity canary passed: ${ROOT}/summary.json"
