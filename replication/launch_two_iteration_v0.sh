#!/bin/bash
# Launch the authorized replication-v0 pilot: one chain, at most two begun sessions.
set -euo pipefail
umask 077

usage() {
  echo "usage: AAR_CLAUDE_SPEND_CAP_USD=<cap> AAR_GPT_JUDGE_SPEND_CAP_USD=<cap> $0 <retained-attempt>/attempt.env" >&2
  exit 2
}

[ "$#" = 1 ] || usage
: "${AAR_CLAUDE_SPEND_CAP_USD:?pass the authorized Claude USD cap in the environment}"
: "${AAR_GPT_JUDGE_SPEND_CAP_USD:?pass the authorized GPT judge USD cap in the environment}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
attempt_env="$(realpath -e -- "$1")"
expected_base="/checkpoint/ram/aar/${USER:?}/sycophancy-gemma4-31b-single-v0/baseline_attempts"

# submit_baseline_v0.sh creates a single, inert export. Refuse arbitrary shell
# input here because this file is supplied on the command line and then sourced.
[ "$(grep -cve '^[[:space:]]*$' "${attempt_env}")" = 1 ] || {
  echo "attempt.env must contain exactly one non-empty line" >&2
  exit 2
}
grep -Eq '^export AAR_RUNTIME_ROOT=/checkpoint/ram/aar/[A-Za-z0-9._-]+/sycophancy-gemma4-31b-single-v0/baseline_attempts/[A-Za-z0-9._-]+$' \
  "${attempt_env}" || {
  echo "attempt.env is not a retained replication-v0 baseline selector" >&2
  exit 2
}
# shellcheck disable=SC1090  # validated retained selector supplied by the operator
source "${attempt_env}"

attempt_root="$(realpath -e -- "${AAR_RUNTIME_ROOT}")"
[ "${attempt_env}" = "${attempt_root}/attempt.env" ] || {
  echo "attempt.env must live at the root it selects" >&2
  exit 2
}
case "${attempt_root}" in
  "${expected_base}"/*) ;;
  *) echo "attempt is outside ${expected_base}: ${attempt_root}" >&2; exit 2 ;;
esac
[ "$(dirname -- "${attempt_root}")" = "${expected_base}" ] || {
  echo "attempt must be one directory below ${expected_base}" >&2
  exit 2
}

# Source env_v0 only after selecting the retained attempt: it derives the
# baseline override and holdout paths from AAR_RUNTIME_ROOT.
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_v0.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
export AAR_TEAM_ID=sycophancy-gemma4_31b-opus48-twoiter-v0
export AAR_EVAL_TIME=14:00:00
export AAR_EVAL_IDLE_SECONDS=50400

[ "$(git -C "${REPO}" branch --show-current)" = uv ] || {
  echo "two-iteration launcher requires branch uv" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "two-iteration launcher requires a clean tracked worktree" >&2
  exit 2
fi
[ "${AAR_RUNTIME_ROOT}" = "${attempt_root}" ] || {
  echo "runtime root drifted from selected attempt" >&2
  exit 2
}

baseline_manifest="${AAR_RUNTIME_ROOT}/metadata/manifest-baseline.json"
for required in \
  "${AAR_BASELINE_OVERRIDES}" \
  "${HOLDOUT_DIR}/sycophancy/sycophancy.yaml" \
  "${baseline_manifest}"; do
  [ -s "${required}" ] || {
    echo "completed retained baseline artifact is missing: ${required}" >&2
    exit 2
  }
done
"${HARNESS_PY}" - "${baseline_manifest}" <<'PY'
import json
import os
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
if manifest.get("phase") != "baseline":
    raise SystemExit("retained manifest is not a completed baseline")
if manifest.get("model_identity") != "google/gemma-4-31B-it":
    raise SystemExit("retained baseline used the wrong target model")
if manifest.get("judge") != {"backend": "model_api", "model": "gpt-5-6-luna"}:
    raise SystemExit("retained baseline used the wrong judge route")
if manifest.get("suite_benchmarks") != [
    "sycophancy_eval", "sycon_fp", "mmlu", "gsm8k", "ifeval"
]:
    raise SystemExit("retained baseline used the wrong benchmark suite")
recorded = manifest.get("authorized_spend_caps_usd", {}).get("gpt_judges")
if recorded != os.environ["AAR_GPT_JUDGE_SPEND_CAP_USD"]:
    raise SystemExit("GPT judge cap differs from the retained baseline authorization")
PY

markers=(environment.ok gpu.ok evaluator_gpu.ok web.ok)
present=0
for marker in "${markers[@]}"; do
  [ ! -f "${AAR_RUNTIME_ROOT}/preflight/${marker}" ] || present=$((present + 1))
done
if [ "${present}" -ne 0 ] && [ "${present}" -ne "${#markers[@]}" ]; then
  echo "partial preflight state found in retained attempt; refusing to overwrite it" >&2
  exit 2
fi

wait_for_job() {
  local job_id="$1" state start now
  local max_wait="${AAR_PREFLIGHT_WAIT_SECONDS:-21600}"
  case "${max_wait}" in ''|*[!0-9]*) echo "AAR_PREFLIGHT_WAIT_SECONDS must be an integer" >&2; return 2;; esac
  start="$(date +%s)"
  while true; do
    state="$(sacct -X -n -P -j "${job_id}" --format=State 2>/dev/null | head -n 1 | cut -d'|' -f1)"
    state="${state%%+*}"
    state="${state%% *}"
    case "${state}" in
      COMPLETED) return 0 ;;
      ''|PENDING|RUNNING|CONFIGURING|COMPLETING|REQUEUED|RESIZING|SUSPENDED) ;;
      *) echo "preflight job ${job_id} failed with state ${state}" >&2; return 1 ;;
    esac
    now="$(date +%s)"
    [ $((now - start)) -lt "${max_wait}" ] || {
      echo "timed out waiting for preflight job ${job_id}" >&2
      return 1
    }
    sleep 20
  done
}

mkdir -p "${AAR_RUNTIME_ROOT}/metadata"
preflight_log="${AAR_RUNTIME_ROOT}/metadata/two_iteration_preflight_submission.txt"
if [ "${present}" = 0 ]; then
  [ ! -e "${preflight_log}" ] || {
    echo "refusing to overwrite ${preflight_log}" >&2
    exit 2
  }
  bash "${SCRIPT_DIR}/submit_preflights_v0.sh" --include-web | tee "${preflight_log}"
  for key in env_setup gpu_preflight eval_gpu_preflight web_preflight; do
    job_id="$(sed -n "s/^${key}=//p" "${preflight_log}")"
    job_id="${job_id%%;*}"
    [[ "${job_id}" =~ ^[0-9]+$ ]] || {
      echo "could not parse ${key} job id from ${preflight_log}" >&2
      exit 2
    }
    wait_for_job "${job_id}"
  done
fi
for marker in "${markers[@]}"; do
  [ -s "${AAR_RUNTIME_ROOT}/preflight/${marker}" ] || {
    echo "required preflight marker is missing: ${AAR_RUNTIME_ROOT}/preflight/${marker}" >&2
    exit 2
  }
done

# Recheck live Serve API, keys, caps, measured baseline, and every retained marker
# immediately before any evaluator or research job is submitted.
"${HARNESS_PY}" "${SCRIPT_DIR}/preflight_v0.py" --launch

submission_log="${AAR_RUNTIME_ROOT}/metadata/launch_two_iteration_submission.txt"
[ ! -e "${submission_log}" ] || {
  echo "refusing to overwrite ${submission_log}" >&2
  exit 2
}
[ ! -e "${AAR_RUNTIME_ROOT}/aar_teams/${AAR_TEAM_ID}" ] || {
  echo "refusing to reuse pilot team ${AAR_TEAM_ID}" >&2
  exit 2
}
bash "${REPO}/scripts/launch_team.sh" "pilot" 2 12 | tee "${submission_log}"
"${HARNESS_PY}" "${SCRIPT_DIR}/record_manifest_v0.py" \
  --phase two-iteration-pilot --submission-log "${submission_log}"
