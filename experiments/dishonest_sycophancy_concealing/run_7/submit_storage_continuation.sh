#!/bin/bash
# Submit the five-chain storage continuation after a verified canary proof.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
RECOVERY_BASE="/storage/home/winnieyangwn/aar-recovery/run7_20261007T004406Z-1b3303d02821"
RECOVERY_BUNDLE="${AAR_RUN7_RECOVERY_BUNDLE:-${RECOVERY_BASE}/baseline_salvage}"
RECOVERY_BUNDLE="$(realpath -e -- "${RECOVERY_BUNDLE}")"
REUSED_BASELINE="${RECOVERY_BUNDLE}/gemma4_31b_multidimensional_baseline.json"
RECOVERED_SOURCES="${RECOVERY_BUNDLE}/source_artifacts"
SNAPSHOT_ROOT="${AAR_RUN7_CLAUDE_SNAPSHOT:-${RECOVERY_BASE}/open_fd_salvage_20261007T0802Z/claude_project_snapshot}"
SNAPSHOT_ROOT="$(realpath -e -- "${SNAPSHOT_ROOT}")"
CANARY_PROOF="${AAR_RUN7_CANARY_PROOF:?set AAR_RUN7_CANARY_PROOF to the verified canary_passed.json}"
CANARY_PROOF="$(realpath -e -- "${CANARY_PROOF}")"
SECRET_ENV="${AAR_RUN7_SECRET_ENV:-/storage/home/winnieyangwn/aar-worktrees/uv/.env}"
SECRET_ENV="$(realpath -e -- "${SECRET_ENV}")"

[ "$(git -C "${REPO}" branch --show-current)" = multi_vllm ] || {
  echo "Run 7 continuation requires branch multi_vllm" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "Run 7 continuation requires a clean tracked worktree" >&2
  exit 2
fi
if [ -n "$(git -C "${REPO}" status --porcelain --untracked-files=all -- \
  aar benchmark_docs scripts replication pyproject.toml uv.lock \
  experiments/dishonest_sycophancy_concealing/run_7)" ]; then
  echo "Run 7 continuation refuses modified launch-critical files" >&2
  exit 2
fi
[ -x "${REPO}/.venv/bin/python" ] || {
  echo "Run 7 continuation requires its worktree-local ARM64 environment" >&2
  exit 2
}
"${REPO}/.venv/bin/python" -c \
  'import platform; assert platform.machine() == "aarch64"'
for proof_field in status canary_git_commit score_result_pair fail_closed_markers merge_manifest_retained ephemeral_merge_removed; do
  [ "$(jq -r --arg field "${proof_field}" '.[$field] // empty' "${CANARY_PROOF}")" != "" ] || {
    echo "canary proof is missing ${proof_field}" >&2
    exit 2
  }
done
[ "$(jq -r '.status' "${CANARY_PROOF}")" = passed ] || {
  echo "canary proof is not passed" >&2
  exit 2
}
for proof_boolean in score_result_pair fail_closed_markers merge_manifest_retained ephemeral_merge_removed; do
  [ "$(jq -r --arg field "${proof_boolean}" '.[$field]' "${CANARY_PROOF}")" = true ] || {
    echo "canary proof did not establish ${proof_boolean}" >&2
    exit 2
  }
done
canary_commit="$(jq -r '.canary_git_commit' "${CANARY_PROOF}")"
commit="$(git -C "${REPO}" rev-parse HEAD)"
git -C "${REPO}" merge-base --is-ancestor "${canary_commit}" "${commit}" || {
  echo "continuation commit does not descend from the canary-tested commit" >&2
  exit 2
}

source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${source_root}" --verify-only >/dev/null
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
export AAR_REPO="${REPO}"
export HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
for secret_name in HF_TOKEN MODEL_API_KEY ANTHROPIC_API_KEY; do
  [ -n "${!secret_name:-}" ] || {
    echo "Run 7 continuation requires nonempty ${secret_name} in ${HARNESS_ENV}" >&2
    exit 2
  }
done
"${REPO}/.venv/bin/python" \
  "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null

short_commit="$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${short_commit}"
attempt_parent="/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/full_attempts"
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir -p "${attempt_parent}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
chmod 700 "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
cp -- "${CANARY_PROOF}" "${attempt_dir}/metadata/canary_passed.json"
"${SCRIPT_DIR}/snapshot_vllm_runtime.sh" "${attempt_dir}" \
  > "${attempt_dir}/metadata/vllm_runtime_path.txt"
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

export AAR_RUNTIME_ROOT="${attempt_dir}"
export AAR_RUN_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}"
export AAR_REUSED_BASELINE="${REUSED_BASELINE}"
export AAR_RECOVERED_BASELINE_SOURCES="${RECOVERED_SOURCES}"
export AAR_RUN7_CLAUDE_SNAPSHOT="${SNAPSHOT_ROOT}"
job_id="$(sbatch --parsable \
  --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=16 --mem=128G --time=02:00:00 \
  --job-name=aar-run7-storage-continuation-launch \
  --output="${attempt_dir}/logs/pipeline-%j.out" \
  --export=AAR_REPO="${REPO}",AAR_RUNTIME_ROOT="${attempt_dir}",AAR_RUN_ATTEMPT_DIR="${attempt_dir}",AAR_BASELINE_GIT_COMMIT="${commit}",AAR_REUSED_BASELINE="${REUSED_BASELINE}",AAR_RECOVERED_BASELINE_SOURCES="${RECOVERED_SOURCES}",AAR_RUN7_CLAUDE_SNAPSHOT="${SNAPSHOT_ROOT}",HARNESS_ENV="${HARNESS_ENV}",LLM_UNCERTAINTY_SRC="${LLM_UNCERTAINTY_SRC}",LLM_UNCERTAINTY_SOURCE_MANIFEST="${LLM_UNCERTAINTY_SOURCE_MANIFEST}",USER="${USER}" \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_7/storage_continuation.sbatch")"
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\ncanary_proof=%s\nold_chain_jobs=%s\nresearch_chains=5\nremaining_sessions=alpha:43,beta:44,gamma:45,delta:44,epsilon:44\nevaluator_jobs=5\nevaluator_gpus_per_job=4\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${CANARY_PROOF}" \
  "1742199 1742200 1742201 1742202 1742203" | tee \
  "${attempt_dir}/metadata/submission.txt"
