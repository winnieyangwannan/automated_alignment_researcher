#!/bin/bash
#SBATCH --job-name=run9-production-recovery
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=08:30:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through recovery/submit_production.sh}"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:?missing Run 9 attempt root}"
AUTODATA="${AAR_AUTODATA_CHECKOUT:?missing pinned AutoData checkout}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:?missing broker interpreter}"
EXECUTION_ID="${AAR_PRODUCTION_EXECUTION_ID:?missing production execution id}"
CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:?missing concurrency}"
MAX_SECONDS="${AAR_SPEEDUP_MAX_SECONDS:-0}"
ATTEMPT_LABEL="${AAR_SPEEDUP_ATTEMPT_LABEL:?missing speed-up attempt label}"
EXPECTED_AAR_SHA="${AAR_EXPECTED_AAR_SHA:?missing expected AAR revision}"
EXPECTED_AUTODATA_SHA="${AAR_EXPECTED_AUTODATA_SHA:?missing expected AutoData revision}"
KIMI_PROXY_INFO="${AAR_KIMI_PROXY_INFO:?missing Kimi proxy contract}"
export PYTHONPATH="${REPO}${PYTHONPATH:+:${PYTHONPATH}}"

TEAM_ID=run9-gemma4-31b-opus48-autodata-five-success-v1
TEAM_DIR="${ATTEMPT_DIR}/aar_teams/${TEAM_ID}"
NATIVE_DIR="${TEAM_DIR}/autodata/native"
RETAINED_STATE="${NATIVE_DIR}/state.db"
ARTIFACTS="${NATIVE_DIR}/artifacts"
WORKSPACES="${NATIVE_DIR}/workspaces"
CONTROL_FILE="${NATIVE_DIR}/production-recovery-control.json"
STATUS_FILE="${NATIVE_DIR}/production-recovery-status.json"
LOCK_FILE="${NATIVE_DIR}/production-recovery.lock"
BROKER_ROOT="${TEAM_DIR}/autodata/broker"
BROKER_ARCHIVE_DIR="${BROKER_ROOT}/attempt-ledgers"
BROKER_ATTEMPT_RETAINED="${BROKER_ARCHIVE_DIR}/${ATTEMPT_LABEL}.db"
CAPABILITY_FILE="${BROKER_ROOT}/capability"
MODEL_ENV="${ATTEMPT_DIR}/secrets/model-api.env"
CAMPAIGN_POLICY_SOURCE="${ATTEMPT_DIR}/metadata/autodata-campaign-policy.json"
METRICS_DIR="${TEAM_DIR}/logs/production-speedup"
METRICS_FILE="${METRICS_DIR}/${ATTEMPT_LABEL}.jsonl"
SUPERVISOR_LOG="${METRICS_DIR}/${ATTEMPT_LABEL}-supervisor.log"
BROKER_LOG="${METRICS_DIR}/${ATTEMPT_LABEL}-broker.log"
SUPERVISOR="${REPO}/scripts/autodata_lifecycle_supervisor.py"
AUTH_BRIDGE="${REPO}/scripts/loopback_model_auth_bridge.py"

case "${CONCURRENCY}" in 16|24|32|64) ;; *) echo "unsupported concurrency" >&2; exit 2;; esac
case "${MAX_SECONDS}" in ''|*[!0-9]*) echo "invalid observation duration" >&2; exit 2;; esac
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_AAR_SHA}" ] || { echo "AAR revision changed" >&2; exit 2; }
[ "$(git -C "${AUTODATA}" rev-parse HEAD)" = "${EXPECTED_AUTODATA_SHA}" ] || { echo "AutoData revision changed" >&2; exit 2; }
[ "$(git -C "${AUTODATA}" branch --show-current)" = main ] || { echo "AutoData recovery checkout must use branch main" >&2; exit 2; }
for required in "${RETAINED_STATE}" "${CAPABILITY_FILE}" "${MODEL_ENV}" "${CAMPAIGN_POLICY_SOURCE}" "${SUPERVISOR}" "${AUTH_BRIDGE}" "${KIMI_PROXY_INFO}" "${BROKER_PYTHON}"; do
  [ -e "${required}" ] || { echo "missing recovery input: ${required}" >&2; exit 2; }
done

mkdir -p "${METRICS_DIR}" "${ARTIFACTS}" "${WORKSPACES}" "${BROKER_ARCHIVE_DIR}"
chmod 700 "${METRICS_DIR}" "${ARTIFACTS}" "${WORKSPACES}" "${BROKER_ARCHIVE_DIR}"
LOCAL_ROOT="${SLURM_TMPDIR:-/tmp}/run9-production-${SLURM_JOB_ID}"
LOCAL_STATE="${LOCAL_ROOT}/native/state.db"
LOCAL_BROKER="${LOCAL_ROOT}/broker/broker.db"
CAMPAIGN_POLICY="${LOCAL_ROOT}/campaign-policy.json"
mkdir -p "$(dirname -- "${LOCAL_STATE}")" "$(dirname -- "${LOCAL_BROKER}")"
chmod 700 "${LOCAL_ROOT}" "$(dirname -- "${LOCAL_STATE}")" "$(dirname -- "${LOCAL_BROKER}")"

export AUTODATA_CACHE_DIR="${ATTEMPT_DIR}/autodata/plugin-cache"
mkdir -p "${AUTODATA_CACHE_DIR}"
chmod 700 "${AUTODATA_CACHE_DIR}"
WRAPPER_PYTHON="$(AUTODATA_CACHE_DIR="${AUTODATA_CACHE_DIR}" "${BROKER_PYTHON}" "${AUTODATA}/plugin/autodata/scripts/bootstrap.py")"
[ -x "${WRAPPER_PYTHON}" ] || { echo "plugin bootstrap failed" >&2; exit 2; }
"${WRAPPER_PYTHON}" -c 'import autodata,autodata.engine; assert autodata.__version__ == "1.0.0"'

BACKUP_MARKER="${NATIVE_DIR}/speedup-baseline.sha256"
if [ ! -f "${BACKUP_MARKER}" ]; then
  baseline="${NATIVE_DIR}/state.pre-speedup.$(date -u +%Y%m%dT%H%M%SZ).db"
  cp --reflink=auto --preserve=mode,timestamps "${RETAINED_STATE}" "${baseline}"
  sha256sum "${baseline}" > "${BACKUP_MARKER}.tmp.${SLURM_JOB_ID}"
  mv -- "${BACKUP_MARKER}.tmp.${SLURM_JOB_ID}" "${BACKUP_MARKER}"
fi
if [ ! -f "${RETAINED_STATE}.snapshot.json" ]; then
  "${REPO}/.venv/bin/python" "${SUPERVISOR}" snapshot --state "${RETAINED_STATE}" --retained-state "${RETAINED_STATE}" --reason speedup-bootstrap >/dev/null
fi
sidecar_archive="${NATIVE_DIR}/stale-sidecars/${ATTEMPT_LABEL}"
for suffix in -wal -shm; do
  if [ -f "${RETAINED_STATE}${suffix}" ]; then
    mkdir -p "${sidecar_archive}"
    chmod 700 "${NATIVE_DIR}/stale-sidecars" "${sidecar_archive}"
    cp --preserve=mode,timestamps "${RETAINED_STATE}${suffix}" "${sidecar_archive}/state.db${suffix}"
  fi
done
"${REPO}/.venv/bin/python" "${SUPERVISOR}" restore --state "${LOCAL_STATE}" --retained-state "${RETAINED_STATE}" --require-manifest >/dev/null
"${REPO}/.venv/bin/python" - \
  "${LOCAL_STATE}" "${CAMPAIGN_POLICY_SOURCE}" "${CAMPAIGN_POLICY}" \
  "${EXECUTION_ID}" "${METRICS_DIR}/${ATTEMPT_LABEL}-routing.json" \
  "${CONCURRENCY}" <<'PY'
import datetime
import hashlib
import json
import pathlib
import sqlite3
import sys

state = pathlib.Path(sys.argv[1])
source_policy = pathlib.Path(sys.argv[2])
target_policy = pathlib.Path(sys.argv[3])
execution_id_text = sys.argv[4]
receipt_path = pathlib.Path(sys.argv[5])
desired_concurrency = int(sys.argv[6])
if desired_concurrency not in {16, 24, 32}:
    raise RuntimeError("unsupported repaired execution concurrency")
bridge_url = "http://127.0.0.1:30611/v1"
with sqlite3.connect(state) as database:
    row = database.execute(
        "SELECT executionJson FROM executions WHERE id=?", (execution_id_text,)
    ).fetchone()
    if row is None:
        raise RuntimeError("production execution vanished during routing repair")
    original = json.loads(row[0])
    repaired = json.loads(row[0])
    environment = repaired["executor"]["non_secret_env"]
    previous_url = environment.get("AUTODATA_GENERATOR_URL")
    if previous_url not in {
        "http://fair-cw-use2-1-ingress-slurm-ingress/v1",
        bridge_url,
    }:
        raise RuntimeError("unexpected generator URL; refusing routing repair")
    environment["AUTODATA_GENERATOR_URL"] = bridge_url
    environment["AUTODATA_GENERATOR_HOST_HEADER"] = ""
    previous_concurrency = repaired.get("concurrency")
    repaired["concurrency"] = desired_concurrency
    database.execute(
        "UPDATE executions SET executionJson=?,updatedAt=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(repaired, sort_keys=True, separators=(",", ":")), execution_id_text),
    )

policy = json.loads(source_policy.read_text(encoding="utf-8"))
policy_environment = policy["required_solve_env"]
policy_environment["AUTODATA_GENERATOR_URL"] = bridge_url
policy_environment["AUTODATA_GENERATOR_HOST_HEADER"] = ""
target_policy.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
target_policy.chmod(0o600)

canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
record = {
    "schema": "aar.autodata.infrastructure-routing-repair/v1",
    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "execution_id": execution_id_text,
    "field": "executor.non_secret_env.AUTODATA_GENERATOR_URL",
    "reason": "cluster gateway returned HTTP 503; use authenticated loopback bridge to the unchanged Kimi deployment",
    "old_execution_sha256": hashlib.sha256(canonical(original)).hexdigest(),
    "new_execution_sha256": hashlib.sha256(canonical(repaired)).hexdigest(),
    "old_url": previous_url,
    "new_url": bridge_url,
    "old_concurrency": previous_concurrency,
    "new_concurrency": desired_concurrency,
    "generator_model": environment["AUTODATA_GENERATOR_MODEL"],
    "generator_deployment_id": environment["AUTODATA_GENERATOR_DEPLOYMENT_ID"],
}
receipt_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
receipt_path.chmod(0o600)
PY
# Broker idempotency is scoped to one recovery attempt.  Native AutoData state
# is the durable authority for completed tasks.  Reusing a transport ledger
# across attempts can turn an intentional routing repair into HTTP 409 when an
# old idempotency key names a different broker job specification.

export AAR_AUTODATA_STATE="${LOCAL_STATE}"
export AAR_AUTODATA_RETAINED_STATE="${RETAINED_STATE}"
export AAR_AUTODATA_ARTIFACTS="${ARTIFACTS}"
export AAR_AUTODATA_WORKSPACES="${WORKSPACES}"
export AAR_AUTODATA_CAPABILITY
AAR_AUTODATA_CAPABILITY="$(<"${CAPABILITY_FILE}")"
# The frozen execution manifest records this loopback port. Bind recovery to it
# rather than rewriting immutable execution provenance.
export AAR_AUTODATA_BROKER_URL=http://127.0.0.1:30610

broker_pid=''
supervisor_pid=''
bridge_pid=''
snapshot_broker() {
  [ -f "${LOCAL_BROKER}" ] || return 0
  "${BROKER_PYTHON}" -c 'import os,pathlib,sqlite3,sys; source=pathlib.Path(sys.argv[1]); retained=pathlib.Path(sys.argv[2]); temporary=retained.with_name(retained.name+".tmp."+str(os.getpid())); source_db=sqlite3.connect("file:"+str(source)+"?mode=ro",uri=True); destination_db=sqlite3.connect(temporary); source_db.backup(destination_db); destination_db.close(); source_db.close(); check=sqlite3.connect("file:"+str(temporary)+"?mode=ro",uri=True); assert check.execute("PRAGMA quick_check").fetchall()==[("ok",)]; check.close(); temporary.chmod(0o600); os.replace(temporary,retained)' "${LOCAL_BROKER}" "${BROKER_ATTEMPT_RETAINED}"
}
cleanup() {
  status=$?
  trap - EXIT INT TERM
  if [ -n "${supervisor_pid}" ] && kill -0 "${supervisor_pid}" 2>/dev/null; then
    kill "${supervisor_pid}" 2>/dev/null || true
    wait "${supervisor_pid}" 2>/dev/null || true
  fi
  "${REPO}/.venv/bin/python" "${SUPERVISOR}" snapshot --state "${LOCAL_STATE}" --retained-state "${RETAINED_STATE}" --reason "speedup-cleanup-${ATTEMPT_LABEL}" >/dev/null || true
  if [ -n "${broker_pid}" ] && kill -0 "${broker_pid}" 2>/dev/null; then
    kill "${broker_pid}" 2>/dev/null || true
    wait "${broker_pid}" 2>/dev/null || true
  fi
  snapshot_broker || true
  if [ -n "${bridge_pid}" ] && kill -0 "${bridge_pid}" 2>/dev/null; then
    kill "${bridge_pid}" 2>/dev/null || true
    wait "${bridge_pid}" 2>/dev/null || true
  fi
  exit "${status}"
}
trap cleanup EXIT INT TERM

"${REPO}/.venv/bin/python" "${AUTH_BRIDGE}" \
  --proxy-info "${KIMI_PROXY_INFO}" --port 30611 \
  >"${METRICS_DIR}/${ATTEMPT_LABEL}-auth-bridge.log" 2>&1 &
bridge_pid=$!
for _ in $(seq 1 30); do
  if "${REPO}/.venv/bin/python" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:30611/healthz",timeout=2).read()' 2>/dev/null; then break; fi
  kill -0 "${bridge_pid}" 2>/dev/null || { echo "Kimi auth bridge exited during startup" >&2; exit 2; }
  sleep 1
done
kill -0 "${bridge_pid}" 2>/dev/null || { echo "Kimi auth bridge is not running" >&2; exit 2; }

PYTHONPATH="${AUTODATA}/src" "${BROKER_PYTHON}" -m autodata.broker.cli \
  --runner local-bwrap --root "${BROKER_ROOT}" --database "${LOCAL_BROKER}" \
  --host 127.0.0.1 --port 30610 --max-concurrent "${CONCURRENCY}" \
  --auth-token-file "${CAPABILITY_FILE}" --workload-env-file "${MODEL_ENV}" \
  --campaign-policy "${CAMPAIGN_POLICY}" --anonymous-registry docker.io \
  >"${BROKER_LOG}" 2>&1 &
broker_pid=$!
for _ in $(seq 1 60); do
  if "${REPO}/.venv/bin/python" -c 'import os,urllib.request; r=urllib.request.Request(os.environ["AAR_AUTODATA_BROKER_URL"]+"/healthz",headers={"Authorization":"Bearer "+os.environ["AAR_AUTODATA_CAPABILITY"]}); urllib.request.urlopen(r,timeout=2).read()' 2>/dev/null; then break; fi
  kill -0 "${broker_pid}" 2>/dev/null || { echo "broker exited during startup" >&2; exit 2; }
  sleep 1
done
kill -0 "${broker_pid}" 2>/dev/null || { echo "broker is not running" >&2; exit 2; }

"${REPO}/.venv/bin/python" "${SUPERVISOR}" register --state "${LOCAL_STATE}" --retained-state "${RETAINED_STATE}" --control-file "${CONTROL_FILE}" --subject-kind execution --subject-id "${EXECUTION_ID}" >/dev/null
"${REPO}/.venv/bin/python" "${SUPERVISOR}" run \
  --python "${WRAPPER_PYTHON}" --state "${LOCAL_STATE}" --retained-state "${RETAINED_STATE}" \
  --control-file "${CONTROL_FILE}" --artifacts "${ARTIFACTS}" --workspaces "${WORKSPACES}" \
  --lock-file "${LOCK_FILE}" --status-file "${STATUS_FILE}" --log-file "${SUPERVISOR_LOG}" \
  --snapshot-interval-seconds 60 --production-timeout-seconds 90000 &
supervisor_pid=$!

started=$(date +%s)
supervisor_exit=0
while true; do
  supervisor_state="$(ps -o stat= -p "${supervisor_pid}" 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -z "${supervisor_state}" ] || [[ "${supervisor_state}" = Z* ]]; then
    set +e
    wait "${supervisor_pid}"
    supervisor_exit=$?
    set -e
    supervisor_pid=''
    break
  fi
  now=$(date +%s)
  metric="$("${REPO}/.venv/bin/python" -c '
import json,pathlib,sqlite3,sys
state,broker,execution,label,elapsed=sys.argv[1:]
with sqlite3.connect(f"file:{state}?mode=ro",uri=True) as db:
    row=db.execute("SELECT status,phase,taskAttemptsUsed,updatedAt FROM executions WHERE id=?",(execution,)).fetchone()
    completed=db.execute("SELECT count(*) FROM events WHERE scopeId=? AND kind=\"task_attempt.completed\"",(execution,)).fetchone()[0]
    succeeded=db.execute("SELECT count(DISTINCT taskId) FROM task_attempts WHERE scopeId=? AND outcome=\"succeeded\"",(execution,)).fetchone()[0]
jobs={}
if pathlib.Path(broker).is_file():
    with sqlite3.connect(f"file:{broker}?mode=ro",uri=True) as db:
        jobs=dict(db.execute("SELECT status,count(*) FROM jobs GROUP BY status"))
print(json.dumps({"attempt":label,"elapsed_seconds":int(elapsed),"status":row[0],"phase":row[1],"attempts_used":row[2],"updated_at":row[3],"completed_events":completed,"succeeded_tasks":succeeded,"broker_jobs":jobs},sort_keys=True))
' "${LOCAL_STATE}" "${LOCAL_BROKER}" "${EXECUTION_ID}" "${ATTEMPT_LABEL}" "$((now - started))")"
  printf '%s\n' "${metric}" | tee -a "${METRICS_FILE}"
  status="$("${REPO}/.venv/bin/python" -c 'import sqlite3,sys; c=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True); print(c.execute("SELECT status FROM executions WHERE id=?",(sys.argv[2],)).fetchone()[0])' "${LOCAL_STATE}" "${EXECUTION_ID}")"
  [ "${status}" = active ] || break
  if [ "${MAX_SECONDS}" -gt 0 ] && [ "$((now - started))" -ge "${MAX_SECONDS}" ]; then
    echo "speed-up observation window reached ${MAX_SECONDS}s"
    break
  fi
  sleep 10
done

if [ "${supervisor_exit}" -ne 0 ]; then
  exit "${supervisor_exit}"
fi
