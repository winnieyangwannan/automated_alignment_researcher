#!/bin/bash
# Launch run 2: five concurrent one-session research chains sharing one fresh team.
set -euo pipefail
umask 077

usage() {
  echo "usage: $0 <retained-attempt>/attempt.env" >&2
  exit 2
}

[ "$#" = 1 ] || usage
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
attempt_env="$(realpath -e -- "$1")"
expected_base="/checkpoint/ram/aar/${USER:?}/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts"

[ "$(grep -cve '^[[:space:]]*$' "${attempt_env}")" = 1 ] || {
  echo "attempt.env must contain exactly one non-empty line" >&2
  exit 2
}
grep -Eq '^export AAR_RUNTIME_ROOT=/checkpoint/ram/aar/[A-Za-z0-9._-]+/honesty-sycophancy-concealing-gemma4-31b-v0/baseline_attempts/[A-Za-z0-9._-]+$' \
  "${attempt_env}" || {
  echo "attempt.env is not a retained three-axis baseline selector" >&2
  exit 2
}
# shellcheck disable=SC1090
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
  echo "attempt must be exactly one directory below ${expected_base}" >&2
  exit 2
}

# Reuse the completed schema-v2 literature cache. Do not refresh or mutate it.
export LITREVIEW_CACHE_ROOT="/checkpoint/ram/aar/${USER}/honesty-sycophancy-gemma4-31b-v0/librarian"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

export AAR_TEAM_ID="honesty-sycophancy-concealing-gemma4_31b-opus48-fiveparallel-run2-v0"
export AAR_CLAUDE_SPEND_CAP_USD=500
export AAR_GPT_JUDGE_SPEND_CAP_USD=500
# Five independent SDK sessions at USD 100 each are the enforceable Claude cap.
export AAR_CLAUDE_SESSION_BUDGET_USD=100
# Recreating an overloaded SDK client would reset max_budget_usd.
export OVERLOADED_MAX_RETRIES=0
export AAR_REQUIRE_SUCCESSFUL_ITERATIONS=1
export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=0
export AAR_FUNCTIONAL_SMOKE=1
export AAR_MULTIDIM_SCORING_CONFIRMED=1
# Permit one training lane per research chain. Slurm may still queue jobs.
export AAR_MAX_CONCURRENT_TRAIN_JOBS=5
# The evaluator serializes five candidates; each 13-leg evaluation can take ~14h.
export AAR_EVAL_TIME=7-00:00:00
export AAR_EVAL_IDLE_SECONDS=604200

[ "$(git -C "${REPO}" branch --show-current)" = uv ] || {
  echo "run 2 requires branch uv" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "run 2 requires a clean tracked worktree" >&2
  exit 2
fi
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all -- \
  aar benchmark_docs scripts replication pyproject.toml uv.lock)" ]; then
  echo "run 2 refuses untracked or modified launch-critical files" >&2
  exit 2
fi
[ "${AAR_RUNTIME_ROOT}" = "${attempt_root}" ] || {
  echo "runtime root drifted from the selected retained attempt" >&2
  exit 2
}

baseline_manifest="${AAR_RUNTIME_ROOT}/metadata/manifest-baseline.json"
suite="${HOLDOUT_DIR}/honesty_sycophancy_concealing_uncertainty/honesty_sycophancy_concealing_uncertainty.yaml"
for required in "${AAR_BASELINE_OVERRIDES}" "${suite}" "${baseline_manifest}" \
  "${LIT_AXIS_DIR}/manifest.json"; do
  [ -s "${required}" ] || {
    echo "required retained artifact is missing: ${required}" >&2
    exit 2
  }
done

for marker in environment.ok gpu.ok evaluator_gpu.ok web.ok; do
  [ -s "${AAR_RUNTIME_ROOT}/preflight/${marker}" ] || {
    echo "required retained preflight marker is missing: ${marker}" >&2
    exit 2
  }
done

# Fail if this account cannot submit to the requested QOS. An empty MaxTRESPU is
# unlimited; any explicit GPU limit must permit the run's 4 eval + 5 train GPUs.
assoc_qos="$(sacctmgr -nP show assoc user="${USER}" account="${AAR_SLURM_ACCOUNT}" format=QOS 2>/dev/null | head -n 1)"
case ",${assoc_qos}," in
  *,"${AAR_AGENT_QOS}",*) ;;
  *) echo "account ${AAR_SLURM_ACCOUNT} is not associated with QOS ${AAR_AGENT_QOS}" >&2; exit 2 ;;
esac
qos_tres="$(sacctmgr -nP show qos "${AAR_AGENT_QOS}" format=MaxTRESPU 2>/dev/null | head -n 1)"
if [[ "${qos_tres}" =~ gres/gpu=([0-9]+) ]] && [ "${BASH_REMATCH[1]}" -lt 9 ]; then
  echo "QOS ${AAR_AGENT_QOS} permits only ${BASH_REMATCH[1]} GPUs per user; run 2 needs up to 9" >&2
  exit 2
fi

"${HARNESS_PY}" "${REPO}/replication/preflight_multidimensional.py" \
  --validate-artifacts-only --launch-profile parallel-five
"${HARNESS_PY}" "${REPO}/replication/preflight_multidimensional.py" \
  --launch --launch-profile parallel-five

metadata_dir="${AAR_RUNTIME_ROOT}/metadata"
team_dir="${AAR_RUNTIME_ROOT}/aar_teams/${AAR_TEAM_ID}"
submission_log="${metadata_dir}/launch_run2_five_parallel_submission.txt"
manifest="${metadata_dir}/manifest-five-parallel.json"
mkdir -p "${metadata_dir}"
exec 9>"${metadata_dir}/launch_run2_five_parallel.lock"
flock -n 9 || { echo "another run-2 launcher owns the launch lock" >&2; exit 2; }

# A fully recorded prior launch is an idempotent no-op. Any partial state is
# ambiguous and fails closed so an operator can repair it without duplicate spend.
if [ -e "${team_dir}" ] || [ -e "${submission_log}" ] || [ -e "${manifest}" ]; then
  if [ -d "${team_dir}" ] && [ -s "${submission_log}" ] && [ -s "${manifest}" ] && \
     [ "$(jq -r '.team_id // empty' "${manifest}")" = "${AAR_TEAM_ID}" ] && \
     [ "$(jq -r '.phase // empty' "${manifest}")" = five-parallel ] && \
     [ "$(jq -r '.job_ids | length' "${manifest}")" = 6 ]; then
    echo "run 2 is already launched; retained submission record: ${submission_log}"
    cat "${submission_log}"
    exit 0
  fi
  echo "partial or inconsistent run-2 launch state exists; refusing duplicate submission" >&2
  echo "team=${team_dir} log=${submission_log} manifest=${manifest}" >&2
  exit 2
fi

bash "${REPO}/scripts/launch_team.sh" "alpha beta gamma delta epsilon" 1 167 \
  | tee "${submission_log}"
"${HARNESS_PY}" "${REPO}/replication/record_manifest_v0.py" \
  --phase five-parallel --submission-log "${submission_log}"
echo "run 2 launched: ${team_dir}"
