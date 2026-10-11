#!/bin/bash
# Submit Run 14: Run 12-style Kimi AAR without AutoData.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN14_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO="$(cd -- "${RUN14_DIR}/../../.." && pwd)"
CANONICAL_CONFIG="$(realpath -e -- "${RUN14_DIR}/config/run.yaml")"
RUN_CONFIG="$(realpath -e -- "${AAR_RUN_CONFIG:-${CANONICAL_CONFIG}}")"
MODE="${AAR_RUN14_MODE:-full}"
case "${MODE}" in full|canary) ;; *) echo "AAR_RUN14_MODE must be full or canary" >&2; exit 2;; esac
[ "${MODE}" != full ] || [ "${RUN_CONFIG}" = "${CANONICAL_CONFIG}" ] || {
  echo "Run 14 full mode requires the canonical run YAML" >&2
  exit 2
}

[ -x "${REPO}/.venv/bin/python" ] || { echo "missing worktree-local runtime" >&2; exit 2; }
SECRET_ENV="$(realpath -e -- "${AAR_RUN14_SECRET_ENV:-${REPO}/.env}")"
RECOVERY_BUNDLE="$(realpath -e -- "${AAR_RUN14_RECOVERY_BUNDLE:-/storage/home/${USER:?}/aar-recovery/run7_20261007T004406Z-1b3303d02821/baseline_salvage}")"
REUSED_BASELINE="${RECOVERY_BUNDLE}/gemma4_31b_multidimensional_baseline.json"
RECOVERED_SOURCES="${RECOVERY_BUNDLE}/source_artifacts"

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}" AAR_RUN_CONFIG="${RUN_CONFIG}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
eval "$("${REPO}/.venv/bin/python" "${REPO}/scripts/load_aar_run_config.py" "${RUN_CONFIG}")"
[ "${AAR_AUTODATA:?missing data-generation backend}" = 0 ] || {
  echo "Run 14 requires data_generation.backend=native" >&2
  exit 2
}
while IFS= read -r name; do unset "${name}"; done < <(compgen -A variable AAR_AUTODATA_)
export AAR_AUTODATA=0

validate_lifecycle_proof() {
  local proof="$1" expected_chains="$2"
  [ "$(jq -r '.status' "${proof}")" = passed ] || {
    echo "lifecycle proof is not passed: ${proof}" >&2; exit 2;
  }
  [ "$(jq -r '.lifecycle_chain_count' "${proof}")" = "${expected_chains}" ] || {
    echo "lifecycle proof expected ${expected_chains} chain(s): ${proof}" >&2
    exit 2
  }
  for field in score_result_pair fail_closed_markers merge_manifest_retained \
    ephemeral_merge_removed kimi_mcp_tool_roundtrip method_gpu_smoke \
    adapter_reload_validation on_demand_evaluator evaluation_item_contract \
    autodata_disabled; do
    [ "$(jq -r --arg field "${field}" '.[$field]' "${proof}")" = true ] || {
      echo "lifecycle proof did not prove ${field}" >&2; exit 2;
    }
  done
  git -C "${REPO}" merge-base --is-ancestor \
    "$(jq -r '.canary_git_commit' "${proof}")" HEAD || {
      echo "current commit does not descend from lifecycle commit" >&2; exit 2;
    }
}

PREREQUISITE_PROOF=""
if [ "${MODE}" = canary ] && \
   [ "${AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT:-0}" -gt 0 ]; then
  PREREQUISITE_PROOF="$(realpath -e -- \
    "${AAR_RUN14_PREREQUISITE_PROOF:?five-chain canary requires the one-chain proof}")"
  validate_lifecycle_proof \
    "${PREREQUISITE_PROOF}" "${AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT}"
fi

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 14 requires branch autodata" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
for required in "${REUSED_BASELINE}" "${RECOVERED_SOURCES}" "${TARGET_MODEL_PATH}"; do
  [ -e "${required}" ] || { echo "required artifact missing: ${required}" >&2; exit 2; }
done
for secret_name in HF_TOKEN MODEL_API_KEY; do
  [ -n "${!secret_name:-}" ] || { echo "Run 14 requires ${secret_name}" >&2; exit 2; }
done

source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${source_root}" --verify-only >/dev/null
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null

storage_root="${AAR_RUN_STORAGE_ROOT:?run config did not set storage.root}"
case "${storage_root}" in /checkpoint/ram/aar/"${USER}"/run14_native_generation) ;; *)
  echo "unexpected Run 14 storage root: ${storage_root}" >&2; exit 2;;
esac
attempt_kind=full_attempts
[ "${MODE}" != canary ] || attempt_kind=canary_attempts
mkdir -p "${storage_root}/${attempt_kind}"
commit="$(git -C "${REPO}" rev-parse HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt="${storage_root}/${attempt_kind}/${attempt_id}"
mkdir "${attempt}"
mkdir -p "${attempt}/"{metadata,logs,runtime}
chmod 700 "${attempt}" "${attempt}/"{metadata,logs}
cp -- "${RUN_CONFIG}" "${attempt}/metadata/run.yaml"
[ -z "${PREREQUISITE_PROOF}" ] || \
  cp -- "${PREREQUISITE_PROOF}" \
    "${attempt}/metadata/prerequisite_lifecycle_passed.json"
"${REPO}/experiments/dishonest_sycophancy_concealing/run_10/runtime/snapshot_vllm_runtime.sh" "${attempt}" \
  > "${attempt}/metadata/vllm_runtime_path.txt"

export PATH="/storage/home/${USER}/tools/node-v22.22.0-linux-arm64/bin:${PATH}"
export KIMI_CLI_PATH="/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi"
export AAR_WEB_MODE=native_web
export AAR_KIMI_SERVE_DEPLOYMENT=steerability_8-kimi26 AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT="/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2"
export KIMI_MODEL_CAPABILITIES=tool_use KIMI_MODEL_MAX_CONTEXT_SIZE=262144
export KIMI_MODEL_MAX_OUTPUT_SIZE=65536 KIMI_MODEL_MAX_COMPLETION_TOKENS=65536
unset KIMI_AGENT_MODEL
timeout 420 "${REPO}/.venv/bin/python" \
  "${REPO}/experiments/dishonest_sycophancy_concealing/run_10/canary/verify_kimi_endpoint.py" \
  --workspace "${REPO}" --output "${attempt}/metadata/kimi_mcp_preflight.json" \
  --timeout-seconds "${AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS:-180}" \
  --cache-ttl-seconds "${AAR_KIMI_PREFLIGHT_CACHE_TTL_SECONDS:-21600}"

export AAR_RUN_ATTEMPT_DIR="${attempt}" AAR_RUNTIME_ROOT="${attempt}"
export AAR_BASELINE_GIT_COMMIT="${commit}" AAR_REUSED_BASELINE="${REUSED_BASELINE}"
export AAR_RECOVERED_BASELINE_SOURCES="${RECOVERED_SOURCES}"
export AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY}"
export AAR_RUN14_MODE="${MODE}"
pipeline_time=02:00:00
[ "${MODE}" != canary ] || pipeline_time=04:00:00
job="$(sbatch --parsable --time="${pipeline_time}" \
  --output="${attempt}/logs/pipeline-%j.out" --export=ALL \
  "${RUN14_DIR}/slurm/pipeline.sbatch")"

submitted_at_pt="$(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z')"
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nmode=%s\nlifecycle_name=%s\nsubmitted_at_pt=%s\nresearch_backend=%s\nresearch_model=Kimi-K2.6\ndata_generation_backend=native\nautodata=0\nseeds=%s\ntarget_score_result_pairs=%s\n' \
  "${job}" "${attempt}" "${commit}" "${MODE}" "${AAR_LIFECYCLE_NAME:-none}" \
  "${submitted_at_pt}" "${AAR_AGENT_BACKEND}" "${AAR_RESEARCH_SEEDS}" \
  "${AAR_TARGET_SUCCESSFUL_ITERATIONS}" | tee "${attempt}/metadata/submission.txt"
unset MODEL_API_KEY HF_TOKEN
