#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
RECOVERY_BUNDLE="${AAR_RUN13_RECOVERY_BUNDLE:-/storage/home/${USER:?}/aar-recovery/run7_20261007T004406Z-1b3303d02821/baseline_salvage}"
RECOVERY_BUNDLE="$(realpath -e -- "${RECOVERY_BUNDLE}")"
REUSED_BASELINE="${RECOVERY_BUNDLE}/gemma4_31b_multidimensional_baseline.json"
RECOVERED_SOURCES="${RECOVERY_BUNDLE}/source_artifacts"
SECRET_ENV="$(realpath -e -- "${AAR_RUN13_SECRET_ENV:-${REPO}/.env}")"
CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:-/usr/local/bin/claude}"

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || { echo "Run 13 requires branch autodata" >&2; exit 2; }
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
[ -x "${REPO}/.venv/bin/python" ] || { echo "missing worktree-local ARM64 .venv" >&2; exit 2; }
[ -x "${CLAUDE_CLI_PATH}" ] || { echo "missing Claude CLI" >&2; exit 2; }
[ "$(stat -c %a "${SECRET_ENV}")" = 600 ] || { echo "secret env must be mode 600" >&2; exit 2; }
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" "${SCRIPT_DIR}/run_13_research_canary.sbatch"; do
  [ -e "${required}" ] || { echo "missing required input: ${required}" >&2; exit 2; }
done

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || { echo "missing ${secret_name}" >&2; exit 2; }
done
"${CLAUDE_CLI_PATH}" --help 2>&1 | grep -q -- --secure-internet-mode || {
  echo "Claude CLI lacks secure-internet mode" >&2
  exit 2
}

source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${source_root}" --verify-only >/dev/null
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null

commit="$(git -C "${REPO}" rev-parse HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_dir="/storage/home/${USER}/aar-runs/run13-claude/research_canary_attempts/${attempt_id}"
mkdir -p "${attempt_dir}"/{metadata,logs,secrets}
chmod 700 "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs" "${attempt_dir}/secrets"
"${REPO}/experiments/dishonest_sycophancy_concealing/run_10/snapshot_vllm_runtime.sh" \
  "${attempt_dir}" > "${attempt_dir}/metadata/vllm_runtime_path.txt"

export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
export AAR_RUNTIME_ROOT="${attempt_dir}" AAR_RUN_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}" AAR_REUSED_BASELINE="${REUSED_BASELINE}"
export AAR_RECOVERED_BASELINE_SOURCES="${RECOVERED_SOURCES}"
export CLAUDE_CLI_PATH

job_id="$(sbatch --parsable \
  --output="${attempt_dir}/logs/pipeline-%j.out" --export=ALL \
  "${SCRIPT_DIR}/run_13_research_canary.sbatch")"
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nresearch_backend=claude\nresearch_model=claude-opus-4-8\nresearch_chains=1\nmax_iterations_per_chain=1\nevaluator_jobs=1\nevaluator_gpus_per_job=4\nkeep_checkpoints=1\n' \
  "${job_id}" "${attempt_dir}" "${commit}" | tee "${attempt_dir}/metadata/submission.txt"
unset MODEL_API_KEY ANTHROPIC_API_KEY HF_TOKEN
