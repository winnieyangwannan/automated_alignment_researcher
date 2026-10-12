#!/bin/bash
#SBATCH --job-name=aar-chain
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=48:00:00
#SBATCH --output=slurm-%x-%j.out
#
# The chain is CPU-only. Training is always submitted as a separate GPU job by
# scripts/submit_train_job.sh; the evaluator is another independently allocated job.
# Launch one autonomous AAR chain against a safety-axis submit-model suite. The axis
# (suite, held-out, property, objective, seed, target model) comes from scripts/axis_env.sh
# (default sycophancy; override with AXIS=<name> -> scripts/axis/<name>.env).
# The agent (Claude) iteratively writes methods, trains a model, then calls the
# evaluate_model tool which STAGES the model and POLLS for scores — a separate
# eval worker (running as the secret-holding user) does the scoring against the
# mode-700 holdout. This chain runs as the research user and never reads the
# holdout. Run several with different --job-name for N parallel chains that see
# each other on the leaderboard.
#
# PREREQ: an eval worker must be draining the queue. As the eval user, run once:
#   sbatch scripts/eval_worker.sh sycophancy
#
# Usage: sbatch --job-name=aar-syco-v1 scripts/slurm_aar_chain.sh <seed_name> [max_hours]

set -euo pipefail
SEED="${1:-explore}"
MAX_H="${2:-47}"               # wall-clock safety (under the 48h Slurm limit)
MAX_ITERS="${3:-500}"         # hard cap on iterations (= sessions) per chain (default 500 as of 2026-06-20; the 47h walltime usually binds before this)
# TEAM_ID scopes the forum: every AAR in the SAME team launch shares one forum
# and accumulates into it; a NEW team (next launch) gets its OWN new forum. The
# team launcher (scripts/launch_team.sh) generates one TEAM_ID and passes it to
# every chain. Fallback below is only for a one-off single-chain run.
TEAM_ID="${4:-${TEAM_ID:-team-$(date +%Y%m%d-%H%M%S)}}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
elif [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/aar" ]; then
  REPO="$(cd -- "${SLURM_SUBMIT_DIR}" && pwd)"
elif [ -d "${SCRIPT_DIR}/../aar" ]; then
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
else
  echo "[aar] ERROR: repository not found; set AAR_REPO or submit from the repository root" >&2
  exit 2
fi
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

# --- harness wiring ---
# PER-AXIS CONFIG lives in ONE place: scripts/axis_env.sh (sourced here). It sets
# PROMPT_TEMPLATE, SUITE_NAME, HELD_OUT_BENCH, SAFETY_PROPERTY, SAFETY_OBJECTIVE,
# SEED_METHOD, TARGET_MODEL — the complete axis swap surface. The team launcher sources
# the SAME file, so they can't disagree. Switch axes by editing axis_env.sh or running
# with AXIS=<name> (scripts/axis/<name>.env). The prompt is generic — it renders the
# property/objective/benchmarks from these + benchmark_docs/<SUITE_NAME>/baseline.json.
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
export HARNESS_TRANSPORT=fs
# Hardened isolation: do NOT export HOLDOUT_DIR here — the research user (this
# job, and the agent it spawns) cannot read the holdout. The eval worker reads
# it. The agent's evaluate_model tool stages the model and polls for scores.
export EVAL_VIA_WORKER=true
export LOCAL_MODE=true            # no S3 / no RunPod / no central server
export AAR_MODE=true
export FULL_AUTO_MAX_RUNTIME_SECONDS=$(( MAX_H * 3600 ))
export MAX_ITERATIONS="${MAX_ITERS}"   # stop after this many iterations (whichever first)
export FORUM_BACKEND=fs           # default under LOCAL_MODE; explicit for clarity
# ===========================================================================
# ONE FOLDER PER TEAM. Everything this team produces lives under TEAM_DIR=
# aar_teams/<TEAM_ID>/ — findings (forum/), the train/eval queue (submissions/,
# scores/), generated method code (methods/), logs/, and the team's OWN in-run
# literature (litreview/). The launcher exports these; we honor them (`:-`) and
# fall back to deriving from TEAM_DIR so a one-off single-chain run also consolidates.
# (Exception: the axis-wide literature BASELINE is shared per-axis at aar_litreview/<axis>/.)
# ===========================================================================
export TEAM_DIR="${TEAM_DIR:-${AAR_RUNTIME_ROOT}/aar_teams/${TEAM_ID}}"
mkdir -p "${TEAM_DIR}"/{forum,submissions,scores,methods,logs,litreview,_train}
# Privileged service diagnostics are always retained outside researcher-facing
# logs.  This must not depend on the optional process-isolation mode: otherwise
# a native transition failure becomes irrecoverably opaque.
mkdir -p "${TEAM_DIR}/secrets/failure-evidence"
chmod 700 "${TEAM_DIR}/secrets" "${TEAM_DIR}/secrets/failure-evidence"
_aar_auth_bridge_log="${TEAM_DIR}/secrets/failure-evidence/autodata-kimi-auth-bridge-${SLURM_JOB_ID:-$$}.log"
_aar_broker_log="${TEAM_DIR}/secrets/failure-evidence/autodata-broker.log"
_aar_supervisor_log="${TEAM_DIR}/secrets/failure-evidence/autodata-lifecycle-supervisor.log"
export LOCAL_FINDINGS_DIR="${LOCAL_FINDINGS_DIR:-${TEAM_DIR}/forum}"
export SUBMISSIONS_DIR="${SUBMISSIONS_DIR:-${TEAM_DIR}/submissions}"
export SCORES_DIR="${SCORES_DIR:-${TEAM_DIR}/scores}"
export AAR_IDEAS_DIR="${AAR_IDEAS_DIR:-${TEAM_DIR}/methods}"      # where the agent writes method packages
export SESSION_LOGS_DIR="${SESSION_LOGS_DIR:-${TEAM_DIR}/logs}"   # per-session transcripts (config.LOGS_DIR)
export LIT_FORUM_DIR="${LIT_FORUM_DIR:-${TEAM_DIR}/litreview}"    # team's OWN in-run lit (private)
export LIT_AXIS_DIR="${LIT_AXIS_DIR:-${REPO}/_runs/litreview/${AXIS:-sycophancy}}"  # axis baseline (read-only)
echo "[aar] team=${TEAM_ID}  TEAM_DIR=${TEAM_DIR}"
echo "[aar] forum=${LOCAL_FINDINGS_DIR}  methods=${AAR_IDEAS_DIR}  lit(team)=${LIT_FORUM_DIR}  lit(axis)=${LIT_AXIS_DIR}"

# AutoData broker readiness is probed before the later research-agent setup, so
# establish the trusted harness interpreter before either path can use it.
PY="${HARNESS_PY}"
[ -x "${PY}" ] || { echo "[aar] ERROR: Python is not executable: ${PY}" >&2; exit 2; }

_autodata_broker_pid=''
_autodata_bridge_pid=''
_autodata_broker_database=''
_autodata_broker_database_retained=''
_autodata_watchdog_pid=''
_autodata_supervisor_pid=''
_autodata_native_state=''
_autodata_native_state_retained=''
_aar_chain_pid="$$"
_aar_research_started=0
_aar_research_pid=''
_aar_research_started_at_epoch=0
_aar_termination_signal=""
_aar_termination_category=""
_aar_research_pid_file="${TEAM_DIR}/logs/.research-process-${SLURM_JOB_ID:-$$}.pid"
snapshot_autodata_broker_database() {
  if [ -n "${_autodata_broker_database}" ] \
      && [ -f "${_autodata_broker_database}" ] \
      && [ -n "${_autodata_broker_database_retained}" ]; then
    "${PY}" "${REPO}/scripts/autodata_broker_ledger.py" snapshot \
      --source "${_autodata_broker_database}" \
      --retained "${_autodata_broker_database_retained}" >/dev/null
  fi
}
stop_child_bounded() {
  local pid="$1" label="$2"
  [ -n "${pid}" ] || return 0
  kill -0 "${pid}" 2>/dev/null || { wait "${pid}" 2>/dev/null || true; return 0; }
  kill -TERM "${pid}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "${pid}" 2>/dev/null; then
    echo "[aar] WARN: ${label} ignored TERM; sending KILL" >&2
    kill -KILL "${pid}" 2>/dev/null || true
  fi
  wait "${pid}" 2>/dev/null || true
}
cleanup_autodata_broker() {
  stop_child_bounded "${_autodata_watchdog_pid}" "AutoData watchdog"
  stop_child_bounded "${_autodata_supervisor_pid}" "AutoData lifecycle supervisor"
  if [ -n "${_autodata_native_state}" ] \
      && [ -n "${_autodata_native_state_retained}" ] \
      && [ -f "${_autodata_native_state}" ]; then
    "${PY}" "${REPO}/scripts/autodata_lifecycle_supervisor.py" snapshot \
      --state "${_autodata_native_state}" \
      --retained-state "${_autodata_native_state_retained}" \
      --reason chain-cleanup >/dev/null || true
  fi
  stop_child_bounded "${_autodata_broker_pid}" "AutoData broker"
  snapshot_autodata_broker_database || true
  stop_child_bounded "${_autodata_bridge_pid}" "Kimi auth bridge"
}
stop_active_research() {
  local research_pid="${_aar_research_pid}"
  if [ -z "${research_pid}" ] && [ -s "${_aar_research_pid_file}" ]; then
    read -r research_pid < "${_aar_research_pid_file}" || true
  fi
  if [[ "${research_pid}" =~ ^[0-9]+$ ]]; then
    stop_child_bounded "${research_pid}" "research agent"
  fi
}
finalize_aar_chain() {
  local result="$1" category="completed" phase="research"
  trap - EXIT TERM INT HUP USR1 USR2
  set +e
  if [ "${_aar_research_started}" != 1 ]; then
    phase="startup"
  fi
  if [ "${result}" -ne 0 ]; then
    if [ -n "${_aar_termination_signal}" ]; then
      category="${_aar_termination_category}"
    elif [ "${_aar_research_started}" = 1 ]; then
      category="research_process_failure"
    else
      category="configuration_or_startup_failure"
      phase="startup"
    fi
  fi
  "${PY}" - "${TEAM_DIR}/logs/research-session-result-${SLURM_JOB_ID:-$$}.json" \
    "${SLURM_JOB_ID:-}" "${result}" "${category}" "${phase}" \
    "${_aar_termination_signal}" "${TEAM_DIR}" "${SEED#explore-}" \
    "${AAR_TARGET_SUCCESSFUL_ITERATIONS:-0}" \
    "${_aar_research_started_at_epoch}" <<'PY'
import json
import os
import pathlib
import secrets
import sys
from datetime import datetime, timezone

path = pathlib.Path(sys.argv[1])
team = pathlib.Path(sys.argv[7])
seed = sys.argv[8]
target_pairs = int(sys.argv[9] or "0")
research_started_at = int(sys.argv[10] or "0")

summary = None
summary_path = team / "logs" / "run_summary.json"
try:
    if summary_path.stat().st_mtime >= research_started_at:
        candidate = json.loads(summary_path.read_text(encoding="utf-8"))
        if isinstance(candidate, dict):
            summary = candidate
except (OSError, UnicodeDecodeError, json.JSONDecodeError):
    pass

used_sessions = sum(1 for _ in (team / "logs").glob(f"session_*_{seed}_*.log"))
scores = set()
for score_path in (team / "scores").glob("*.json"):
    if score_path.name.endswith(".failed.json"):
        continue
    try:
        score = json.loads(score_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        continue
    run_id = score.get("run_id") if isinstance(score, dict) else None
    scores.add(run_id if isinstance(run_id, str) and run_id else score_path.stem)
findings = set()
for finding_path in (team / ".finding_dedup").glob("runid_*/post.json"):
    try:
        finding = json.loads(finding_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        continue
    run_id = finding.get("run_id") if isinstance(finding, dict) else None
    if isinstance(run_id, str):
        findings.add(run_id)
completed_pairs = len(scores & findings)
stop_reason = summary.get("stop_reason") if summary is not None else None

if completed_pairs >= target_pairs > 0:
    disposition = "complete"
elif sys.argv[4] in {"cancelled", "configuration_or_startup_failure"}:
    disposition = "halt"
elif sys.argv[4] in {"research_process_failure", "runtime_service_failure"}:
    disposition = "recover"
elif int(sys.argv[3]) == 0 and stop_reason in {
    "max_iterations",
    "timeout",
    "orchestration_incident",
    "permanent_session_failure",
}:
    disposition = "recover"
elif int(sys.argv[3]) == 0 and stop_reason == "successful_iterations":
    disposition = "halt"
else:
    disposition = "halt"

value = {
    "schema": "aar.research-session-result/v1",
    "job_id": sys.argv[2] or None,
    "exit_code": int(sys.argv[3]),
    "category": sys.argv[4],
    "phase": sys.argv[5],
    "termination_signal": sys.argv[6] or None,
    "retryable": disposition == "recover",
    "recovery_disposition": disposition,
    "stop_reason": stop_reason,
    "completed_pairs": completed_pairs,
    "used_sessions": used_sessions,
    "finished_at": datetime.now(timezone.utc).isoformat(),
}
path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
directory = os.open(
    path.parent,
    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
)
temporary_name = f".{path.name}.tmp.{secrets.token_hex(16)}"
descriptor = -1
try:
    descriptor = os.open(
        temporary_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=directory,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        descriptor = -1
        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(
        temporary_name,
        path.name,
        src_dir_fd=directory,
        dst_dir_fd=directory,
    )
    os.fsync(directory)
finally:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        os.unlink(temporary_name, dir_fd=directory)
    except FileNotFoundError:
        pass
    os.close(directory)
PY
  # The marker is retained before bounded child cleanup so a scheduler KILL
  # after TERM cannot erase the authoritative cancellation evidence.
  stop_active_research
  cleanup_autodata_broker
  rm -f -- "${_aar_research_pid_file}"
  exit "${result}"
}
terminate_aar_chain() {
  local signal="$1" result="$2" category="$3"
  _aar_termination_signal="${signal}"
  _aar_termination_category="${category}"
  exit "${result}"
}
trap 'finalize_aar_chain "$?"' EXIT
trap 'terminate_aar_chain TERM 143 cancelled' TERM
trap 'terminate_aar_chain INT 130 cancelled' INT
trap 'terminate_aar_chain HUP 129 cancelled' HUP
trap 'terminate_aar_chain USR1 138 cancelled' USR1
# A distinct watchdog signal keeps internal service death separate from an
# operator/scheduler cancellation while sharing the same durable cleanup path.
trap 'terminate_aar_chain USR2 70 runtime_service_failure' USR2
if [ "${AAR_AUTODATA:-0}" = 1 ]; then
  : "${AAR_AUTODATA_CHECKOUT:?missing canonical AutoData checkout}"
  : "${AAR_AUTODATA_PLUGIN_ROOT:?missing pinned AutoData plugin root}"
  : "${AAR_AUTODATA_BROKER_PYTHON:?missing broker Python}"
  : "${AAR_AUTODATA_MODEL_ENV_FILE:?missing model workload env path}"
  : "${AAR_AUTODATA_CAMPAIGN_POLICY:?missing campaign policy}"
  : "${AAR_AUTODATA_TRAINING_DATA_CONTRACT:?missing training-data contract}"
  : "${AAR_AUTODATA_CAPABILITY:?missing attempt-scoped broker capability}"
  : "${AAR_AUTODATA_APPROVAL_PRIVATE_KEY:?missing delegated approval key}"
  : "${AAR_AUTODATA_APPROVAL_PUBLIC_KEY:?missing delegated approval public key}"
  # shellcheck disable=SC1091
  source "${REPO}/scripts/autodata_runtime_profile.sh"
  aar_apply_autodata_runtime_profile
  : "${AAR_AUTODATA_BROKER_RUNNER:?missing broker runner}"
  if [ -n "${AAR_AUTODATA_PROFILE:-}" ]; then
    echo "[aar] AutoData runtime profile verified (profile=${AAR_AUTODATA_PROFILE}, concurrency=${AAR_AUTODATA_CONCURRENCY}, model_attempts=${AAR_AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS}, reuse=${AAR_AUTODATA_REUSE_POLICY})"
  fi
  export AUTODATA_CACHE_DIR="${AUTODATA_CACHE_DIR:-${AAR_RUNTIME_ROOT}/autodata/plugin-cache}"
  mkdir -p "${AUTODATA_CACHE_DIR}"
  chmod 700 "${AUTODATA_CACHE_DIR}"
  export AAR_AUTODATA_WRAPPER_PYTHON
  AAR_AUTODATA_WRAPPER_PYTHON="$(
    AUTODATA_CACHE_DIR="${AUTODATA_CACHE_DIR}" \
      "${AAR_AUTODATA_BROKER_PYTHON}" \
      "${AAR_AUTODATA_PLUGIN_ROOT}/scripts/bootstrap.py"
  )"
  [ -x "${AAR_AUTODATA_WRAPPER_PYTHON}" ] || {
    echo "[aar] ERROR: AutoData plugin bootstrap did not return an executable" >&2
    exit 2
  }
  "${AAR_AUTODATA_WRAPPER_PYTHON}" -c \
    'import autodata,autodata.engine; assert autodata.__version__ == "1.0.0"' || {
      echo "[aar] ERROR: bootstrapped AutoData plugin import failed" >&2
      exit 2
    }
  echo "[aar] AutoData plugin bootstrap verified (cache=attempt-local, interpreter=pinned)"
  _autodata_root="${TEAM_DIR}/autodata/broker"
  mkdir -p "${_autodata_root}"
  chmod 700 "${TEAM_DIR}/autodata" "${_autodata_root}"
  _autodata_broker_database_root="${SLURM_TMPDIR:-/tmp}/aar-autodata-broker-${SLURM_JOB_ID:-$$}"
  mkdir -p "${_autodata_broker_database_root}"
  chmod 700 "${_autodata_broker_database_root}"
  _autodata_broker_database="${_autodata_broker_database_root}/broker.db"
  _autodata_broker_archive="${_autodata_root}/attempt-ledgers"
  mkdir -p "${_autodata_broker_archive}"
  chmod 700 "${_autodata_broker_archive}"
  _autodata_broker_database_retained="${_autodata_broker_archive}/campaign-ledger.db"
  exec 9>"${_autodata_broker_archive}/campaign-ledger.lock"
  flock -n 9 || {
    echo "[aar] ERROR: another session owns the AutoData campaign ledger" >&2
    exit 2
  }
  "${PY}" "${REPO}/scripts/autodata_broker_ledger.py" restore \
    --retained "${_autodata_broker_database_retained}" \
    --destination "${_autodata_broker_database}" >/dev/null
  _autodata_native_state_retained="${TEAM_DIR}/autodata/native/state.db"
  export AAR_AUTODATA_RETAINED_STATE="${_autodata_native_state_retained}"
  if [ "${AAR_AUTODATA_LIFECYCLE_SUPERVISED:-0}" = 1 ]; then
    _autodata_native_database_root="${SLURM_TMPDIR:-/tmp}/aar-autodata-native-${SLURM_JOB_ID:-$$}"
    mkdir -p "${_autodata_native_database_root}"
    chmod 700 "${_autodata_native_database_root}"
    _autodata_native_state="${_autodata_native_database_root}/state.db"
    "${PY}" "${REPO}/scripts/autodata_lifecycle_supervisor.py" restore \
      --state "${_autodata_native_state}" \
      --retained-state "${_autodata_native_state_retained}" \
      --require-manifest >/dev/null
    export AAR_AUTODATA_STATE="${_autodata_native_state}"
  else
    _autodata_native_state="${_autodata_native_state_retained}"
    export AAR_AUTODATA_STATE="${_autodata_native_state}"
  fi
  export AAR_AUTODATA_ARTIFACTS="${TEAM_DIR}/autodata/native/artifacts"
  export AAR_AUTODATA_WORKSPACES="${TEAM_DIR}/autodata/native/workspaces"
  export AAR_AUTODATA_SUPERVISOR_CONTROL="${TEAM_DIR}/autodata/native/lifecycle-control.json"
  export AAR_AUTODATA_SUPERVISOR_STATUS="${TEAM_DIR}/autodata/native/lifecycle-supervisor-status.json"
  export AAR_AUTODATA_APPROVAL_AUDIT_DIR="${TEAM_DIR}/autodata/approvals"
  mkdir -p "$(dirname -- "${AAR_AUTODATA_STATE}")" "${AAR_AUTODATA_ARTIFACTS}" \
    "${AAR_AUTODATA_WORKSPACES}" "${AAR_AUTODATA_APPROVAL_AUDIT_DIR}"
  chmod 700 "${TEAM_DIR}/autodata/native" "${AAR_AUTODATA_ARTIFACTS}" \
    "${AAR_AUTODATA_WORKSPACES}" "${AAR_AUTODATA_APPROVAL_AUDIT_DIR}"
  _autodata_capability_file="${_autodata_root}/capability"
  printf '%s\n' "${AAR_AUTODATA_CAPABILITY}" > "${_autodata_capability_file}"
  chmod 600 "${_autodata_capability_file}"
  _autodata_resume_ports="$(PYTHONPATH="${REPO}${PYTHONPATH:+:${PYTHONPATH}}" \
    "${PY}" -m aar.infrastructure.autodata_resume_ports \
      --state "${AAR_AUTODATA_STATE}" \
      --control "${AAR_AUTODATA_SUPERVISOR_CONTROL}")"
  _autodata_retained_port="$(jq -r '.broker_port // empty' \
    <<<"${_autodata_resume_ports}")"
  _autodata_retained_bridge_port="$(jq -r '.generator_bridge_port // empty' \
    <<<"${_autodata_resume_ports}")"
  if [ -n "${_autodata_retained_port}" ]; then
    _autodata_port="${_autodata_retained_port}"
    echo "[aar] reusing retained AutoData loopback ports for session recovery"
  else
    _autodata_port=$(( 10000 + (${SLURM_JOB_ID:-8791} % 40000) ))
  fi
  export AAR_AUTODATA_BROKER_URL="http://127.0.0.1:${_autodata_port}"
  if [ -n "${AAR_KIMI_PROXY_INFO:-}" ]; then
    [ -f "${AAR_KIMI_PROXY_INFO}" ] || {
      echo "[aar] ERROR: missing Kimi proxy contract: ${AAR_KIMI_PROXY_INFO}" >&2
      exit 2
    }
    if [ -n "${_autodata_retained_bridge_port}" ]; then
      _autodata_bridge_port="${_autodata_retained_bridge_port}"
    else
      _autodata_bridge_port=$(( 50000 + (${SLURM_JOB_ID:-8791} % 15000) ))
    fi
    _autodata_runtime="${TEAM_DIR}/autodata/runtime/${SLURM_JOB_ID:-$$}"
    mkdir -p "${_autodata_runtime}"
    chmod 700 "${TEAM_DIR}/autodata/runtime" "${_autodata_runtime}"
    _autodata_repaired_policy="${_autodata_runtime}/campaign-policy.json"
    "${PY}" - "${AAR_AUTODATA_CAMPAIGN_POLICY}" "${_autodata_repaired_policy}" "${_autodata_bridge_port}" <<'PY'
import json
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
port = int(sys.argv[3])
policy = json.loads(source.read_text(encoding="utf-8"))
environment = policy["required_solve_env"]
environment["AUTODATA_GENERATOR_URL"] = f"http://127.0.0.1:{port}/v1"
environment["AUTODATA_GENERATOR_HOST_HEADER"] = ""
environment.setdefault("AUTODATA_TARGET_ENABLED", "0")
destination.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
destination.chmod(0o600)
PY
    export AAR_AUTODATA_CAMPAIGN_POLICY="${_autodata_repaired_policy}"
    "${PY}" "${REPO}/scripts/loopback_model_auth_bridge.py" \
      --proxy-info "${AAR_KIMI_PROXY_INFO}" --port "${_autodata_bridge_port}" \
      >"${_aar_auth_bridge_log}" 2>&1 &
    _autodata_bridge_pid=$!
    _autodata_bridge_ready=0
    for _autodata_probe in $(seq 1 30); do
      if "${PY}" -c 'import sys,urllib.request; urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/healthz",timeout=2).read()' "${_autodata_bridge_port}" 2>/dev/null; then
        _autodata_bridge_ready=1
        break
      fi
      kill -0 "${_autodata_bridge_pid}" 2>/dev/null || {
        echo "[aar] ERROR: Kimi auth bridge exited during startup" >&2
        exit 2
      }
      sleep 1
    done
    [ "${_autodata_bridge_ready}" = 1 ] || {
      echo "[aar] ERROR: Kimi auth bridge did not become healthy within 30 seconds" >&2
      exit 2
    }
    kill -0 "${_autodata_bridge_pid}" 2>/dev/null || {
      echo "[aar] ERROR: Kimi auth bridge is not running" >&2
      exit 2
    }
    echo "[aar] direct Kimi bridge ready (policy=job-local)"
  fi
  _autodata_broker_args=(
    --runner "${AAR_AUTODATA_BROKER_RUNNER}"
    --root "${_autodata_root}"
    --database "${_autodata_broker_database}"
    --host 127.0.0.1 --port "${_autodata_port}"
    --max-concurrent "${AAR_AUTODATA_CONCURRENCY:?}"
    --auth-token-file "${_autodata_capability_file}"
    --workload-env-file "${AAR_AUTODATA_MODEL_ENV_FILE}"
    --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY}"
    --anonymous-registry docker.io
  )
  if [ "${AAR_AUTODATA_BROKER_RUNNER}" = sandoq-firecracker ]; then
    : "${AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE:?missing SandoQ token path}"
    _autodata_broker_args+=(
      --gateway-url "${SANDOQ_GATEWAY_URL:-https://sandoq-gateway.eks-prod.cf.aws.metafb.cloud}"
      --execsidecar-token-file "${AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE}"
      --no-registry-preflight
    )
  elif [ "${AAR_AUTODATA_BROKER_RUNNER}" != local-bwrap ]; then
    echo "[aar] ERROR: unsupported AutoData broker runner: ${AAR_AUTODATA_BROKER_RUNNER}" >&2
    exit 2
  fi
  PYTHONPATH="${AAR_AUTODATA_CHECKOUT}/src" \
    "${AAR_AUTODATA_BROKER_PYTHON}" -m autodata.broker.cli \
      "${_autodata_broker_args[@]}" \
      > "${_aar_broker_log}" 2>&1 &
  _autodata_broker_pid=$!
  _autodata_broker_ready=0
  for _autodata_probe in $(seq 1 60); do
    if "${PY}" -c 'import os,urllib.request; r=urllib.request.Request(os.environ["AAR_AUTODATA_BROKER_URL"]+"/healthz",headers={"Authorization":"Bearer "+os.environ["AAR_AUTODATA_CAPABILITY"]}); urllib.request.urlopen(r,timeout=2).read()' 2>/dev/null; then
      _autodata_broker_ready=1
      break
    fi
    kill -0 "${_autodata_broker_pid}" 2>/dev/null || {
      echo "[aar] ERROR: AutoData broker exited during startup" >&2
      exit 2
    }
    sleep 1
  done
  [ "${_autodata_broker_ready}" = 1 ] || {
    echo "[aar] ERROR: AutoData broker did not become healthy within 60 seconds" >&2
    exit 2
  }
  kill -0 "${_autodata_broker_pid}" 2>/dev/null || { echo "[aar] ERROR: AutoData broker is not running" >&2; exit 2; }
  echo "[aar] campaign-scoped AutoData broker ready (pid=${_autodata_broker_pid}, runner=${AAR_AUTODATA_BROKER_RUNNER}, concurrency=${AAR_AUTODATA_CONCURRENCY}, database=node-local)"
  if [ "${AAR_AUTODATA_LIFECYCLE_SUPERVISED:-0}" = 1 ]; then
    "${PY}" "${REPO}/scripts/autodata_lifecycle_supervisor.py" run \
      --python "${AAR_AUTODATA_WRAPPER_PYTHON}" \
      --state "${AAR_AUTODATA_STATE}" \
      --retained-state "${AAR_AUTODATA_RETAINED_STATE}" \
      --control-file "${AAR_AUTODATA_SUPERVISOR_CONTROL}" \
      --artifacts "${AAR_AUTODATA_ARTIFACTS}" \
      --workspaces "${AAR_AUTODATA_WORKSPACES}" \
      --training-data-contract "${AAR_AUTODATA_TRAINING_DATA_CONTRACT}" \
      --campaign-policy "${AAR_AUTODATA_CAMPAIGN_POLICY}" \
      --resolved-config "${AAR_AUTODATA_RESOLVED_CONFIG}" \
      --lock-file "${TEAM_DIR}/autodata/native/lifecycle-supervisor.lock" \
      --status-file "${AAR_AUTODATA_SUPERVISOR_STATUS}" \
      --log-file "${_aar_supervisor_log}" \
      --stage-timeout-policy "${AAR_AUTODATA_STAGE_TIMEOUT_POLICY:-enforce}" &
    _autodata_supervisor_pid=$!
    sleep 1
    kill -0 "${_autodata_supervisor_pid}" 2>/dev/null || {
      echo "[aar] ERROR: AutoData lifecycle supervisor exited during startup" >&2
      exit 2
    }
    echo "[aar] AutoData lifecycle supervisor ready (pid=${_autodata_supervisor_pid}, stage_timeout_policy=${AAR_AUTODATA_STAGE_TIMEOUT_POLICY:-enforce}, state=node-local)"
  fi
  (
    abort_active_research() {
      local reason="$1" research_pid=""
      echo "[aar] ERROR: ${reason}" >&2
      if [ -s "${_aar_research_pid_file}" ]; then
        read -r research_pid < "${_aar_research_pid_file}" || true
        if [[ "${research_pid}" =~ ^[0-9]+$ ]]; then
          stop_child_bounded "${research_pid}" "research agent"
        fi
      fi
      kill -USR2 "${_aar_chain_pid}" 2>/dev/null || true
      exit 1
    }
    while sleep 15; do
      if ! kill -0 "${_autodata_broker_pid}" 2>/dev/null; then
        abort_active_research "AutoData broker exited while research was active"
      fi
      if [ -n "${_autodata_bridge_pid}" ] \
          && ! kill -0 "${_autodata_bridge_pid}" 2>/dev/null; then
        abort_active_research "Kimi auth bridge exited while research was active"
      fi
      if [ -n "${_autodata_supervisor_pid}" ] \
          && ! kill -0 "${_autodata_supervisor_pid}" 2>/dev/null; then
        abort_active_research "AutoData lifecycle supervisor exited while research was active"
      fi
      if ! snapshot_autodata_broker_database; then
        abort_active_research "failed to retain the AutoData broker ledger"
      fi
    done
  ) &
  _autodata_watchdog_pid=$!
  unset _autodata_broker_args _autodata_broker_database_root \
    _autodata_broker_ready _autodata_bridge_ready \
    _autodata_capability_file _autodata_probe _autodata_port \
    _autodata_resume_ports _autodata_retained_port \
    _autodata_retained_bridge_port \
    _autodata_native_database_root
fi

# --- agent authentication + web mode ---
# Claude remains the default. Kimi is selected only through
# AAR_AGENT_BACKEND=kimi and uses the Kimi CLI's own configured authentication.
_agent_backend="${AAR_AGENT_BACKEND:-claude}"
_requested_web="${AAR_WEB_MODE:-auto}"
case "${_requested_web}" in auto|meta_secure|native_web) ;; *)
  echo "[aar] ERROR: AAR_WEB_MODE must be auto, meta_secure, or native_web" >&2; exit 2;;
esac
_detected_web=native_web
case "${_agent_backend}" in
  claude)
    if [ -z "${CLAUDE_CLI_PATH:-}" ]; then
      CLAUDE_CLI_PATH="$(command -v claude || true)"
    fi
    if [ -n "${CLAUDE_CLI_PATH:-}" ] && [ -x "${CLAUDE_CLI_PATH}" ]; then
      _cli_help="$("${CLAUDE_CLI_PATH}" --help 2>&1 || true)"
      case "${_cli_help}" in *--secure-internet-mode*) _detected_web=meta_secure;; esac
      unset _cli_help
    fi
    ;;
  kimi)
    if [ -z "${KIMI_CLI_PATH:-}" ]; then
      KIMI_CLI_PATH="$(command -v kimi || true)"
    fi
    [ -x "${KIMI_CLI_PATH:-}" ] || { echo "[aar] ERROR: Kimi backend requires KIMI_CLI_PATH or kimi on PATH" >&2; exit 2; }
    [ "${_requested_web}" != meta_secure ] || { echo "[aar] ERROR: meta_secure web mode is Claude-only" >&2; exit 2; }
    export KIMI_CLI_PATH
    ;;
  *) echo "[aar] ERROR: AAR_AGENT_BACKEND must be claude or kimi" >&2; exit 2;;
esac
if [ "${_requested_web}" = auto ]; then
  export AAR_WEB_MODE="${_detected_web}"
else
  export AAR_WEB_MODE="${_requested_web}"
fi
export AAR_MONITOR_BACKEND="${AAR_MONITOR_BACKEND:-model_api}"
case "${AAR_MONITOR_BACKEND}" in
  model_api)
    export MONITOR_MODEL="${MONITOR_MODEL:-claude-4-8-opus}"
    export AAR_MONITOR_MODEL_API_KEY="${AAR_MONITOR_MODEL_API_KEY:-${MODEL_API_KEY:-}}"
    [ -n "${AAR_MONITOR_MODEL_API_KEY}" ] || {
      echo "[aar] ERROR: Model API monitor needs MODEL_API_KEY in ${HARNESS_ENV}" >&2
      exit 2
    }
    ;;
  anthropic)
    export MONITOR_MODEL="${MONITOR_MODEL:-claude-opus-4-8}"
    export AAR_MONITOR_ANTHROPIC_API_KEY="${AAR_MONITOR_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-${ANT_high_prio_API:-${ANT_API_KEY:-}}}}"
    [ -n "${AAR_MONITOR_ANTHROPIC_API_KEY}" ] || {
      echo "[aar] ERROR: Anthropic monitor needs a direct key in ${HARNESS_ENV}" >&2
      exit 2
    }
    ;;
  *) echo "[aar] ERROR: AAR_MONITOR_BACKEND must be model_api or anthropic" >&2; exit 2;;
esac
if [ "${_agent_backend}" = claude ] && [ "${AAR_WEB_MODE}" = meta_secure ]; then
  [ -x "${CLAUDE_CLI_PATH:-}" ] || { echo "[aar] ERROR: meta_secure requires an executable Claude CLI" >&2; exit 2; }
  [ -x "${REPO}/scripts/aar-paper-search" ] || { echo "[aar] ERROR: paper-search helper is not executable" >&2; exit 2; }
  export CLAUDE_CLI_PATH META_CLAUDE_SECURE_INTERNET_MODE=1
  unset ANTHROPIC_API_KEY
elif [ "${_agent_backend}" = claude ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[aar] ERROR: native_web mode requires ANTHROPIC_API_KEY" >&2
  exit 2
fi
unset _agent_backend _requested_web _detected_web

cd "${REPO}"

# Per-chain MEMORY file (NOT shared between chains), under THIS team's logs/ folder.
# Parallel chains must not read or append each other's AGENT_LOG. Seed an explicit
# iteration-1 stub so a fresh chain reads a REAL "no history" note instead of
# confabulating past results (observed: a fresh chain invented 3 fake prior
# iterations). A fresh team gets a fresh TEAM_DIR, so it always starts clean.
CHAIN_TAG="$(printf '%s' "${MODEL:-qwen}-${SEED}" | tr -cs 'A-Za-z0-9' '_' | sed 's/^_//; s/_$//')"
export AAR_AGENT_LOG_PATH="${SESSION_LOGS_DIR}/AGENT_LOG_${CHAIN_TAG}.md"
mkdir -p "${TEAM_DIR}/timings"
export AAR_PHASE_TIMINGS_PATH="${TEAM_DIR}/timings/chain_${CHAIN_TAG}.jsonl"
if [ ! -f "${AAR_AGENT_LOG_PATH}" ] && [ -n "${AAR_RECOVERED_AGENT_LOG_DIR:-}" ]; then
  _recovered_log_dir="$(realpath -e -- "${AAR_RECOVERED_AGENT_LOG_DIR}")"
  _recovered_log="${_recovered_log_dir}/AGENT_LOG_${CHAIN_TAG}.md"
  [ -f "${_recovered_log}" ] || {
    echo "[aar] ERROR: recovered agent log is missing for ${CHAIN_TAG}" >&2
    exit 2
  }
  cp -- "${_recovered_log}" "${AAR_AGENT_LOG_PATH}"
  chmod 600 "${AAR_AGENT_LOG_PATH}"
  echo "[aar] seeded recovered chain memory from ${_recovered_log}"
  unset _recovered_log_dir _recovered_log
fi
if [ ! -f "${AAR_AGENT_LOG_PATH}" ]; then
  printf '# AGENT_LOG — chain %s\n\n## ITERATION 1 — NO PRIOR HISTORY\nThis chain has run NO prior iterations. You have NO past results, scores, or methods yet.\nDo NOT invent or recall any prior iteration — begin from the literature + leaderboard.\nRecord each iteration below as you complete it.\n' "${SEED}" > "${AAR_AGENT_LOG_PATH}"
fi

# Prompt/dashboard baseline table for THIS axis+model. BASELINES_PATH is set by axis_env.sh
# (tagged by axis+model). If the eval user already published the authoritative per-model
# baselines (publish_holdout.sh, from benchmark_docs), USE IT — don't clobber. Otherwise
# self-provision from the PUBLISHERS fallback (exact for qwen; WARNs for un-measured models).
# Held-out-excluded either way. _format_baselines + the monitor + the dashboard read this path.
if [ -f "${BASELINES_PATH}" ]; then
  echo "[aar] using pre-published baselines: ${BASELINES_PATH}"
else
  _ONLY_ARGS=()
  if [ -n "${AAR_SUITE_BENCHMARKS:-}" ]; then
    _only_text="${AAR_SUITE_BENCHMARKS//,/ }"
    read -r -a _only_names <<< "${_only_text}"
    _ONLY_ARGS=(--only "${_only_names[@]}")
  fi
  "${PY}" scripts/publish_suite.py --emit-prompt-baselines "${BASELINES_PATH}" \
    --suite "${SUITE_NAME}" --target-model "${TARGET_MODEL}" "${_ONLY_ARGS[@]}"
fi

echo "[aar] launching chain seed=${SEED} suite=${SUITE_NAME} target=${TARGET_MODEL} (max ${MAX_H}h)"
# Export IDEA_UID/IDEA_NAME so share_finding's payload tags each forum finding
# with its chain identity (the launcher previously only passed --idea-uid as a
# CLI arg, so findings came back with idea_uid=None — fixed here). RUN_ID is left
# UNSET on purpose so evaluate_model mints a unique per-call id (IDEA_UID+ts).
# MODEL in the identity so a same-axis/different-model team gets distinct session
# ids, method-dir prefixes, and forum finding tags (no cross-team collision).
IDEA_UID="${AAR_IDEA_UID_OVERRIDE:-${MODEL:-qwen}-${SEED}-$(date +%s)}"
export IDEA_UID
export IDEA_NAME="${MODEL:-qwen}-${SEED}"
# The evaluator was launched by the operator before this research job and
# retains its credential environment.  Training needs no provider credential.
# Keep raw credentials and every operator credential-file path out of the
# internet-enabled Claude child; agent.py independently enforces the same rule
# at the SDK subprocess boundary for purpose-specific monitor secrets.
unset MODEL_API_KEY LLAMA_API_KEY HF_TOKEN HUGGING_FACE_HUB_TOKEN OAI_API OPENAI_API_KEY
unset ANTHROPIC_API_KEY ANT_high_prio_API ANT_API_KEY HARNESS_ENV
unset AAR_RUN8_EXECSIDECAR_TOKEN_FILE AAR_RUN8_BROKER_TOKEN_FILE
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN RUNPOD_API_KEY WANDB_API_KEY
if [ "${AAR_AGENT_BACKEND:-claude}" = kimi ]; then
  unset ANTHROPIC_API_KEY ANT_high_prio_API ANT_API_KEY CLAUDE_CLI_PATH
fi
if [ "${AAR_HIDE_EVAL_CONFIG:-0}" = "1" ]; then
  # The evaluator has already inherited what it needs. Do not advertise the
  # run-specific full suite selection or baseline override to the researcher.
  unset HOLDOUT_DIR HELDOUT_SCORES_DIR AAR_SUITE_BENCHMARKS AAR_BASELINE_OVERRIDES
fi
_aar_research_started=1
_aar_research_started_at_epoch="$(date +%s)"
PYTHONUNBUFFERED=1 "${PY}" -u run.py agent --idea-uid "${IDEA_UID}" --idea-name "${IDEA_NAME}" \
  --max-iterations "${MAX_ITERS}" --max-runtime "${FULL_AUTO_MAX_RUNTIME_SECONDS}" --local &
_aar_research_pid=$!
printf '%s\n' "${_aar_research_pid}" > "${_aar_research_pid_file}"
chmod 600 "${_aar_research_pid_file}"
if wait "${_aar_research_pid}"; then
  _aar_research_result=0
else
  _aar_research_result=$?
fi
rm -f -- "${_aar_research_pid_file}"
if [ "${AAR_AUTODATA_COORDINATOR_OWNS_LIFECYCLE:-0}" = 1 ]; then
  [ "${AAR_AUTODATA_LIFECYCLE_SUPERVISED:-0}" = 1 ] || {
    echo "[aar] ERROR: lifecycle ownership requires the AutoData supervisor" >&2
    exit 2
  }
  if [ -z "${_autodata_supervisor_pid}" ] || \
      ! kill -0 "${_autodata_supervisor_pid}" 2>/dev/null; then
    echo "[aar] ERROR: lifecycle supervisor is unavailable after the semantic turn" >&2
    exit 70
  fi
  _aar_lifecycle_marker_name=''
  case "${AAR_AUTODATA_STOP_AFTER:-}" in
    production) _aar_lifecycle_marker_name=production-canary-complete.json ;;
    training_smoke) _aar_lifecycle_marker_name=training-smoke-canary-complete.json ;;
    *)
      echo "[aar] ERROR: coordinator-owned lifecycle has no supported terminal receipt" >&2
      exit 2
      ;;
  esac
  echo "[aar] semantic turn exited status=${_aar_research_result}; lifecycle supervisor remains authoritative until ${AAR_AUTODATA_STOP_AFTER}"
  _aar_lifecycle_next_update=0
  while true; do
    shopt -s nullglob
    _aar_lifecycle_markers=("${TEAM_DIR}"/autodata/*/"${_aar_lifecycle_marker_name}")
    shopt -u nullglob
    if [ "${#_aar_lifecycle_markers[@]}" -eq 1 ]; then
      case "${AAR_AUTODATA_STOP_AFTER}" in
        production)
          jq -e --argjson required "${AAR_AUTODATA_PRODUCTION_ROWS:?}" '
            .schema == "aar.autodata.production-canary-complete/v1"
            and .stop_after == "production"
            and .required_accepted_rows == $required
            and .verification.available_rows >= $required
            and .verification.run_id == .run_id
          ' "${_aar_lifecycle_markers[0]}" >/dev/null || {
            echo "[aar] ERROR: production terminal receipt is invalid" >&2
            exit 2
          }
          ;;
        training_smoke)
          jq -e --argjson required "${AAR_AUTODATA_PRODUCTION_ROWS:?}" '
            .schema == "aar.autodata.training-smoke-canary-complete/v1"
            and .stop_after == "training_smoke"
            and .required_accepted_rows == $required
            and .verification.available_rows >= $required
            and .training.consumed_rows == $required
            and .training.optimizer_steps == 1
            and .verification.run_id == .run_id
          ' "${_aar_lifecycle_markers[0]}" >/dev/null || {
            echo "[aar] ERROR: training-smoke terminal receipt is invalid" >&2
            exit 2
          }
          ;;
      esac
      echo "[aar] verified terminal lifecycle receipt is ready: ${_aar_lifecycle_markers[0]}"
      _aar_research_result=0
      break
    fi
    if [ "${#_aar_lifecycle_markers[@]}" -gt 1 ]; then
      echo "[aar] ERROR: multiple terminal lifecycle receipts are present" >&2
      exit 2
    fi
    kill -0 "${_autodata_supervisor_pid}" 2>/dev/null || {
      wait "${_autodata_supervisor_pid}" 2>/dev/null || true
      echo "[aar] ERROR: lifecycle supervisor exited before its terminal receipt" >&2
      exit 70
    }
    _aar_lifecycle_now="$(date +%s)"
    if [ "${_aar_lifecycle_now}" -ge "${_aar_lifecycle_next_update}" ]; then
      echo "[aar] waiting for coordinator-owned AutoData lifecycle (${AAR_AUTODATA_STOP_AFTER})"
      _aar_lifecycle_next_update=$((_aar_lifecycle_now + 60))
    fi
    sleep 10
  done
  unset _aar_lifecycle_marker_name _aar_lifecycle_markers \
    _aar_lifecycle_next_update _aar_lifecycle_now
fi
[ "${_aar_research_result}" -eq 0 ] || exit "${_aar_research_result}"
if [ "${AAR_VERIFY_TWO_ITERATION_ARTIFACTS:-0}" = 1 ]; then
  "${PY}" "${REPO}/replication/verify_two_iteration_multidimensional.py" \
    --team-dir "${TEAM_DIR}" --expected-iterations 2
fi
echo "=== DONE ==="
