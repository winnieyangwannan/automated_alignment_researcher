#!/bin/bash
#SBATCH --job-name=aar-run9-native-preflight
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=00:30:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through submit_run_9_native_preflight.sh}"
AUTODATA="${AAR_AUTODATA_CHECKOUT:?missing AutoData checkout}"
ROOT="${AAR_RUN9_PREFLIGHT_ROOT:?missing retained preflight root}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:?missing broker Python}"
CAPABILITY_FILE="${AAR_AUTODATA_CAPABILITY_FILE:?missing capability file}"
CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:?missing concurrency}"

port=$((10000 + (${SLURM_JOB_ID:?} % 40000)))
broker_url="http://127.0.0.1:${port}"
broker_database_root="${SLURM_TMPDIR:-/tmp}/aar-run9-native-preflight-${SLURM_JOB_ID}"
broker_database="${broker_database_root}/broker.db"
retained_broker_database="${ROOT}/broker/broker.db"
broker_pid=""

snapshot_broker_database() {
  if [ -f "${broker_database}" ]; then
    "${BROKER_PYTHON}" -c \
      'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall(); c.close()' \
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
}
trap cleanup EXIT INT TERM

mkdir -p "${ROOT}/broker" "${ROOT}/plugin-cache" "${broker_database_root}"
chmod 700 "${ROOT}/broker" "${ROOT}/plugin-cache" "${broker_database_root}"
export AUTODATA_CACHE_DIR="${ROOT}/plugin-cache"
export AAR_AUTODATA_WRAPPER_PYTHON
AAR_AUTODATA_WRAPPER_PYTHON="$(
  AUTODATA_CACHE_DIR="${AUTODATA_CACHE_DIR}" \
    "${BROKER_PYTHON}" "${AAR_AUTODATA_PLUGIN_ROOT:?}/scripts/bootstrap.py"
)"
"${AAR_AUTODATA_WRAPPER_PYTHON}" -c \
  'import autodata,autodata.engine; assert autodata.__version__ == "1.0.0"'

broker_args=(
  --runner local-bwrap
  --root "${ROOT}/broker"
  --database "${broker_database}"
  --host 127.0.0.1 --port "${port}"
  --max-concurrent "${CONCURRENCY}"
  --auth-token-file "${CAPABILITY_FILE}"
  --workload-env-file "${AAR_AUTODATA_MODEL_ENV_FILE:?}"
  --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY:?}"
  --anonymous-registry docker.io
)
PYTHONPATH="${AUTODATA}/src" "${BROKER_PYTHON}" -m autodata.broker.cli \
  "${broker_args[@]}" > "${ROOT}/broker.log" 2>&1 &
broker_pid=$!
for probe in $(seq 1 60); do
  if "${BROKER_PYTHON}" -c \
    'import pathlib,sys,urllib.request; token=pathlib.Path(sys.argv[1]).read_text().strip(); request=urllib.request.Request(sys.argv[2]+"/healthz",headers={"Authorization":"Bearer "+token}); urllib.request.urlopen(request,timeout=2).read()' \
    "${CAPABILITY_FILE}" "${broker_url}" 2>/dev/null; then
    break
  fi
  kill -0 "${broker_pid}" 2>/dev/null || { echo "broker exited during startup" >&2; exit 2; }
  sleep 1
done
kill -0 "${broker_pid}" 2>/dev/null || { echo "broker is not running" >&2; exit 2; }

PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" \
  "${REPO}/scripts/autodata_native_real_e2e.py" \
  --root "${ROOT}/lifecycle" \
  --plugin-root "${AAR_AUTODATA_PLUGIN_ROOT}" \
  --recipe-root "${REPO}/aar/autodata_recipes/dishonest_sycophancy_concealing" \
  --broker-url "${broker_url}" \
  --broker-auth-token-file "${CAPABILITY_FILE}" \
  --model-api-env-file "${AAR_AUTODATA_MODEL_ENV_FILE}" \
  --generator-url "${AAR_AUTODATA_GENERATOR_URL:?}" \
  --generator-host-header "${AAR_AUTODATA_GENERATOR_HOST_HEADER:?}" \
  --task-count 16 \
  --required-rows 1 \
  --concurrency 16 \
  --environment "${AAR_AUTODATA_ENVIRONMENT:?}" \
  --max-cost-usd 2 \
  --timeout-seconds 1200 \
  > "${ROOT}/lifecycle.log" 2>&1

"${REPO}/.venv/bin/python" - "${ROOT}" "${broker_database}" <<'PY'
import json
import pathlib
import sqlite3
import sys

root = pathlib.Path(sys.argv[1])
database = pathlib.Path(sys.argv[2])
report = json.loads((root / "lifecycle" / "report.json").read_text())
if report.get("status") != "passed":
    raise SystemExit("native lifecycle did not pass")
if report.get("task_count") != 16 or report.get("concurrency") != 16:
    raise SystemExit("native lifecycle did not use production concurrency")
if report.get("accepted_rows", 0) < 1:
    raise SystemExit("native lifecycle produced no accepted rows")
if report.get("elapsed_seconds", 9999) > 1200:
    raise SystemExit("native lifecycle exceeded the 20-minute fail-fast ceiling")
with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
    rows = connection.execute("select status from jobs").fetchall()
if len(rows) < 16 or any(status != "SUCCEEDED" for (status,) in rows):
    raise SystemExit("native lifecycle broker jobs were incomplete")
summary = {
    "schema": "aar.autodata.native-preflight/v1",
    "success": True,
    "elapsed_seconds": report["elapsed_seconds"],
    "broker_job_count": len(rows),
    "approval_audits": report["approval_audits"],
    "accepted_rows": report["accepted_rows"],
    "meta_execution_id": report["meta_execution_id"],
    "production_execution_id": report["production_execution_id"],
}
(root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY
chmod 600 "${ROOT}/summary.json"
echo "RUN9_NATIVE_PREFLIGHT_PASS ${ROOT}/summary.json"
