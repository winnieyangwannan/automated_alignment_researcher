#!/bin/bash
# Launch exactly one composed-suite chain, capped at two begun AAR sessions.
set -euo pipefail
umask 077

usage() {
  echo "usage: AAR_MULTIDIM_SCORING_CONFIRMED=1 AAR_CLAUDE_SPEND_CAP_USD=500 AAR_GPT_JUDGE_SPEND_CAP_USD=500 $0 <retained-attempt>/attempt.env" >&2
  exit 2
}

[ "$#" = 1 ] || usage
: "${AAR_CLAUDE_SPEND_CAP_USD:?pass the separately authorized USD 500 Claude cap}"
: "${AAR_GPT_JUDGE_SPEND_CAP_USD:?pass the separately authorized USD 500 GPT judge cap}"
: "${AAR_MULTIDIM_SCORING_CONFIRMED:?explicitly confirm the composed scoring contract}"
[ "${AAR_MULTIDIM_SCORING_CONFIRMED}" = 1 ] || {
  echo "AAR_MULTIDIM_SCORING_CONFIRMED must equal 1" >&2; exit 2;
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
attempt_env="$(realpath -e -- "$1")"
expected_base="/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts"

[ "$(grep -cve '^[[:space:]]*$' "${attempt_env}")" = 1 ] || {
  echo "attempt.env must contain exactly one non-empty line" >&2; exit 2;
}
grep -Eq '^export AAR_RUNTIME_ROOT=/checkpoint/ram/aar/[A-Za-z0-9._-]+/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/[A-Za-z0-9._-]+$' \
  "${attempt_env}" || {
  echo "attempt.env is not a retained multi-dimensional baseline selector" >&2; exit 2;
}
# shellcheck disable=SC1090
source "${attempt_env}"
attempt_root="$(realpath -e -- "${AAR_RUNTIME_ROOT}")"
[ "${attempt_env}" = "${attempt_root}/attempt.env" ] || {
  echo "attempt.env must live at the root it selects" >&2; exit 2;
}
case "${attempt_root}" in
  "${expected_base}"/*) ;;
  *) echo "attempt is outside ${expected_base}: ${attempt_root}" >&2; exit 2 ;;
esac
[ "$(dirname -- "${attempt_root}")" = "${expected_base}" ] || {
  echo "attempt must be one directory below ${expected_base}" >&2; exit 2;
}

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"
export AAR_TEAM_ID=honesty-sycophancy-concealing-gemma4_31b-opus48-twoiter-v0
# One exact 13-benchmark evaluation can exceed 12 hours on two GPUs. Give
# the evaluator and chain enough wall time for two sequential sessions; the
# exact session count and per-session SDK budget remain the binding controls.
export AAR_EVAL_TIME=74:00:00
export AAR_EVAL_IDLE_SECONDS=266400
# Two sessions at USD 250 each hard-bound the Claude Agent SDK spend to the
# separately authorized USD 500 AAR-agent budget.
export AAR_CLAUDE_SESSION_BUDGET_USD=250
# A fresh SDK client would reset max_budget_usd. Disable automatic 529 client
# recreation so USD 250 remains a hard logical-session bound.
export OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1
export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=1
# No separate eval Unix principal is provisioned on this cluster. This makes
# the two-iteration run an orchestration-valid functional smoke; its held-out
# values must not be claimed as scientifically isolated generalization results.
export AAR_FUNCTIONAL_SMOKE=1

[ "$(git -C "${REPO}" branch --show-current)" = uv ] || {
  echo "multi-dimensional launcher requires branch uv" >&2; exit 2;
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "multi-dimensional launcher requires a clean tracked worktree" >&2; exit 2;
fi
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all -- \
  aar benchmark_docs scripts replication pyproject.toml uv.lock)" ]; then
  echo "multi-dimensional launcher refuses untracked or modified launch-critical files" >&2
  exit 2
fi
[ "${AAR_RUNTIME_ROOT}" = "${attempt_root}" ] || {
  echo "runtime root drifted from selected attempt" >&2; exit 2;
}

baseline_manifest="${AAR_RUNTIME_ROOT}/metadata/manifest-baseline.json"
suite="${HOLDOUT_DIR}/honesty_sycophancy_concealing_uncertainty/honesty_sycophancy_concealing_uncertainty.yaml"
for required in "${AAR_BASELINE_OVERRIDES}" "${suite}" "${baseline_manifest}"; do
  [ -s "${required}" ] || {
    echo "completed retained composed-baseline artifact is missing: ${required}" >&2; exit 2;
  }
done
"${HARNESS_PY}" "${SCRIPT_DIR}/preflight_multidimensional.py" --validate-artifacts-only

markers=(environment.ok gpu.ok evaluator_gpu.ok web.ok)
present=0
for marker in "${markers[@]}"; do
  [ ! -f "${AAR_RUNTIME_ROOT}/preflight/${marker}" ] || present=$((present + 1))
done
if [ "${present}" -ne 0 ] && [ "${present}" -ne "${#markers[@]}" ]; then
  echo "partial preflight state found in retained attempt; refusing to overwrite it" >&2; exit 2;
fi

wait_for_job() {
  local job_id="$1" state start now
  local max_wait="${AAR_PREFLIGHT_WAIT_SECONDS:-21600}"
  case "${max_wait}" in
    ''|*[!0-9]*) echo "AAR_PREFLIGHT_WAIT_SECONDS must be an integer" >&2; return 2 ;;
  esac
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
      echo "timed out waiting for preflight job ${job_id}" >&2; return 1;
    }
    sleep 20
  done
}

mkdir -p "${AAR_RUNTIME_ROOT}/metadata"
preflight_log="${AAR_RUNTIME_ROOT}/metadata/multidimensional_two_iteration_preflight_submission.txt"
if [ "${present}" = 0 ]; then
  [ ! -e "${preflight_log}" ] || { echo "refusing to overwrite ${preflight_log}" >&2; exit 2; }
  bash "${SCRIPT_DIR}/submit_preflights_multidimensional.sh" --include-web | tee "${preflight_log}"
  for key in env_setup gpu_preflight eval_gpu_preflight web_preflight; do
    job_id="$(sed -n "s/^${key}=//p" "${preflight_log}")"
    job_id="${job_id%%;*}"
    [[ "${job_id}" =~ ^[0-9]+$ ]] || {
      echo "could not parse ${key} job id from ${preflight_log}" >&2; exit 2;
    }
    wait_for_job "${job_id}"
  done
fi
for marker in "${markers[@]}"; do
  [ -s "${AAR_RUNTIME_ROOT}/preflight/${marker}" ] || {
    echo "required preflight marker is missing: ${AAR_RUNTIME_ROOT}/preflight/${marker}" >&2; exit 2;
  }
done

"${HARNESS_PY}" "${SCRIPT_DIR}/preflight_multidimensional.py" --launch

submission_log="${AAR_RUNTIME_ROOT}/metadata/launch_two_iteration_multidimensional_submission.txt"
[ ! -e "${submission_log}" ] || { echo "refusing to overwrite ${submission_log}" >&2; exit 2; }
[ ! -e "${AAR_RUNTIME_ROOT}/aar_teams/${AAR_TEAM_ID}" ] || {
  echo "refusing to reuse pilot team ${AAR_TEAM_ID}" >&2; exit 2;
}
bash "${REPO}/scripts/launch_team.sh" "pilot" 2 72 | tee "${submission_log}"
"${HARNESS_PY}" "${SCRIPT_DIR}/record_manifest_v0.py" \
  --phase two-iteration-pilot --submission-log "${submission_log}"
