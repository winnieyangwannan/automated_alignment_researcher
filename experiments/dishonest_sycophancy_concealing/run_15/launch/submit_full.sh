#!/bin/bash
# Submit Run 15: Run 12-style Kimi AAR without AutoData.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN15_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO="$(cd -- "${RUN15_DIR}/../../.." && pwd)"
CANONICAL_CONFIG="$(realpath -e -- "${RUN15_DIR}/config/run.yaml")"
ONE_CHAIN_CONFIG="$(realpath -e -- "${RUN15_DIR}/canary/one_chain_lifecycle_check/config/run.yaml")"
FIVE_CHAIN_CONFIG="$(realpath -e -- "${RUN15_DIR}/canary/five_chain_lifecycle_check/config/run.yaml")"
RUN_CONFIG="$(realpath -e -- "${AAR_RUN_CONFIG:-${CANONICAL_CONFIG}}")"
MODE="${AAR_RUN15_MODE:-full}"
case "${MODE}" in full|canary) ;; *) echo "AAR_RUN15_MODE must be full or canary" >&2; exit 2;; esac
[ "${MODE}" != full ] || [ "${RUN_CONFIG}" = "${CANONICAL_CONFIG}" ] || {
  echo "Run 15 full mode requires the canonical run YAML" >&2
  exit 2
}
if [ "${MODE}" = full ]; then
  LIFECYCLE_PROOF_POLICY=required
  if [ "$#" -eq 1 ] && \
     [ "$1" = --user-authorized-without-lifecycle-proofs ]; then
    LIFECYCLE_PROOF_POLICY=user_authorized_bypass
    ONE_CHAIN_PROOF=""
    FIVE_CHAIN_PROOF=""
  elif [ "$#" -eq 2 ]; then
    ONE_CHAIN_PROOF="$(realpath -e -- "$1")"
    FIVE_CHAIN_PROOF="$(realpath -e -- "$2")"
  else
    echo "usage: $0 <one-chain-proof.json> <five-chain-proof.json>" >&2
    echo "   or: $0 --user-authorized-without-lifecycle-proofs" >&2
    exit 2
  fi
else
  [ "$#" -eq 0 ] || {
    echo "Run 15 canary mode takes no positional arguments" >&2
    exit 2
  }
  ONE_CHAIN_PROOF=""
  FIVE_CHAIN_PROOF=""
  LIFECYCLE_PROOF_POLICY=required
fi

[ -x "${REPO}/.venv/bin/python" ] || { echo "missing worktree-local runtime" >&2; exit 2; }
SHARED_HARNESS_PY="${REPO}/.venv/bin/python"
SECRET_ENV="$(realpath -e -- "${AAR_RUN15_SECRET_ENV:-${REPO}/.env}")"
RECOVERY_BUNDLE="$(realpath -e -- "${AAR_RUN15_RECOVERY_BUNDLE:-/storage/home/${USER:?}/aar-recovery/run7_20261007T004406Z-1b3303d02821/baseline_salvage}")"
REUSED_BASELINE="${RECOVERY_BUNDLE}/gemma4_31b_multidimensional_baseline.json"
RECOVERED_SOURCES="${RECOVERY_BUNDLE}/source_artifacts"

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}" AAR_RUN_CONFIG="${RUN_CONFIG}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
eval "$("${REPO}/.venv/bin/python" "${REPO}/scripts/load_aar_run_config.py" "${RUN_CONFIG}")"
[ "${AAR_AUTODATA:?missing data-generation backend}" = 0 ] || {
  echo "Run 15 requires data_generation.backend=native" >&2
  exit 2
}
while IFS= read -r name; do unset "${name}"; done < <(compgen -A variable AAR_AUTODATA_)
export AAR_AUTODATA=0
commit="$(git -C "${REPO}" rev-parse HEAD)"

validate_lifecycle_proof() {
  local proof="$1" expected_chains="$2" expected_lifecycle="$3" expected_config="$4"
  "${REPO}/.venv/bin/python" \
    "${RUN15_DIR}/canary/verify_run_15_canary.py" \
    --validate-proof "${proof}" \
    --expected-chains "${expected_chains}" \
    --expected-lifecycle "${expected_lifecycle}" \
    --expected-config "${expected_config}" \
    --expected-commit "${commit}" >/dev/null
}

PREREQUISITE_PROOF=""
if [ "${MODE}" = canary ] && \
   [ "${AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT:-0}" -gt 0 ]; then
  PREREQUISITE_PROOF="$(realpath -e -- \
    "${AAR_RUN15_PREREQUISITE_PROOF:?five-chain canary requires the one-chain proof}")"
  validate_lifecycle_proof \
    "${PREREQUISITE_PROOF}" "${AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT}" \
    one_chain_native_generation "${ONE_CHAIN_CONFIG}"
fi
if [ "${MODE}" = full ] && [ "${LIFECYCLE_PROOF_POLICY}" = required ]; then
  validate_lifecycle_proof \
    "${ONE_CHAIN_PROOF}" 1 one_chain_native_generation "${ONE_CHAIN_CONFIG}"
  validate_lifecycle_proof \
    "${FIVE_CHAIN_PROOF}" 5 five_chain_lifecycle_check "${FIVE_CHAIN_CONFIG}"
  one_chain_proof_sha256="$(sha256sum -- "${ONE_CHAIN_PROOF}" | awk '{print $1}')"
  [ "$(jq -r '.prerequisite_proof_sha256 // empty' "${FIVE_CHAIN_PROOF}")" = \
    "${one_chain_proof_sha256}" ] || {
    echo "five-chain proof is not bound to the supplied one-chain proof" >&2
    exit 2
  }
fi

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 15 requires branch autodata" >&2
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
  [ -n "${!secret_name:-}" ] || { echo "Run 15 requires ${secret_name}" >&2; exit 2; }
done

storage_root="${AAR_RUN_STORAGE_ROOT:?run config did not set storage.root}"
case "${storage_root}" in /checkpoint/ram/aar/"${USER}"/run15_native_generation) ;; *)
  echo "unexpected Run 15 storage root: ${storage_root}" >&2; exit 2;;
esac
attempt_kind=full_attempts
[ "${MODE}" != canary ] || attempt_kind=canary_attempts
mkdir -p "${storage_root}/${attempt_kind}"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-${commit:0:12}"
attempt="${storage_root}/${attempt_kind}/${attempt_id}"
mkdir "${attempt}"
mkdir -p "${attempt}/"{metadata,logs,runtime}
chmod 700 "${attempt}" "${attempt}/"{metadata,logs}
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${commit}" ] || {
  echo "AAR source changed during launch preflight" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "AAR source became dirty during launch preflight" >&2
  exit 2
fi

SOURCE_REPO="${attempt}/runtime/aar-source"
export PYTHONDONTWRITEBYTECODE=1
"${REPO}/scripts/create_pinned_source_snapshot.sh" \
  "${REPO}" "${commit}" "${SOURCE_REPO}" >/dev/null
[ -x "${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_15/launch/submit_full.sh" ] || {
  echo "Run 15 launcher is absent from the source commit" >&2
  exit 2
}
case "${RUN_CONFIG}" in
  "${REPO}"/*)
    SNAPSHOT_RUN_CONFIG="${SOURCE_REPO}/${RUN_CONFIG#"${REPO}/"}"
    ;;
  *)
    echo "Run 15 config must be tracked inside the source repository" >&2
    exit 2
    ;;
esac
[ -s "${SNAPSHOT_RUN_CONFIG}" ] || {
  echo "attempt-local Run 15 config is missing" >&2
  exit 2
}
cmp -s -- "${RUN_CONFIG}" "${SNAPSHOT_RUN_CONFIG}" || {
  echo "attempt-local Run 15 config differs from the validated config" >&2
  exit 2
}
install -m 400 -- "${SNAPSHOT_RUN_CONFIG}" "${attempt}/metadata/run.yaml"

jq -n \
  --arg aar_commit "${commit}" --arg aar_root "${SOURCE_REPO}" \
  '{schema:"aar.source-snapshots/v1",aar:{commit:$aar_commit,root:$aar_root}}' \
  > "${attempt}/metadata/source-snapshots.json"
chmod 400 "${attempt}/metadata/source-snapshots.json"

shared_source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${SHARED_HARNESS_PY}" "${SOURCE_REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${shared_source_root}" --verify-only >/dev/null
SNAPSHOT_SOURCE_ROOT="${attempt}/runtime/llm-uncertainty-source"
mkdir -p "${SNAPSHOT_SOURCE_ROOT}"
cp -a -- "${shared_source_root}/data" "${SNAPSHOT_SOURCE_ROOT}/data"
install -m 400 -- "${shared_source_root}/.aar-source.json" \
  "${SNAPSHOT_SOURCE_ROOT}/.aar-source.json"
"${SHARED_HARNESS_PY}" "${SOURCE_REPO}/scripts/prepare_llm_uncertainty_source.py" \
  --output-root "${SNAPSHOT_SOURCE_ROOT}" --verify-only >/dev/null
export LLM_UNCERTAINTY_SRC="${SNAPSHOT_SOURCE_ROOT}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${SNAPSHOT_SOURCE_ROOT}/.aar-source.json"

SNAPSHOT_RECOVERY_ROOT="${attempt}/runtime/baseline-recovery"
mkdir -p "${SNAPSHOT_RECOVERY_ROOT}"
install -m 400 -- "${REUSED_BASELINE}" "${SNAPSHOT_RECOVERY_ROOT}/baseline.json"
cp -a -- "${RECOVERED_SOURCES}" "${SNAPSHOT_RECOVERY_ROOT}/source-artifacts"
SNAPSHOT_REUSED_BASELINE="${SNAPSHOT_RECOVERY_ROOT}/baseline.json"
SNAPSHOT_RECOVERED_SOURCES="${SNAPSHOT_RECOVERY_ROOT}/source-artifacts"
"${SHARED_HARNESS_PY}" \
  "${SOURCE_REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${SNAPSHOT_REUSED_BASELINE}" \
  --recovered-source-dir "${SNAPSHOT_RECOVERED_SOURCES}" >/dev/null

[ -z "${PREREQUISITE_PROOF}" ] || \
  cp -- "${PREREQUISITE_PROOF}" \
    "${attempt}/metadata/prerequisite_lifecycle_passed.json"
if [ "${MODE}" = full ] && [ "${LIFECYCLE_PROOF_POLICY}" = required ]; then
  cp -- "${ONE_CHAIN_PROOF}" \
    "${attempt}/metadata/one_chain_lifecycle_passed.json"
  cp -- "${FIVE_CHAIN_PROOF}" \
    "${attempt}/metadata/five_chain_lifecycle_passed.json"
  five_chain_proof_sha256="$(sha256sum -- "${FIVE_CHAIN_PROOF}" | awk '{print $1}')"
  printf 'one_chain_sha256=%s\nfive_chain_sha256=%s\n' \
    "${one_chain_proof_sha256}" "${five_chain_proof_sha256}" \
    > "${attempt}/metadata/lifecycle_proofs.sha256"
elif [ "${MODE}" = full ]; then
  override_recorded_at_pt="$(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z')"
  jq -n \
    --arg recorded_at_pt "${override_recorded_at_pt}" \
    --arg git_commit "${commit}" \
    --arg researcher_deployment "autodata2_8-kimi26" \
    '{schema:"aar.run15-lifecycle-proof-override/v1",
      status:"user_authorized",
      scope:"full-five-chain-5x50",
      recorded_at_pt:$recorded_at_pt,
      git_commit:$git_commit,
      researcher_deployment:$researcher_deployment,
      skipped_proofs:["one_chain_native_generation","five_chain_lifecycle_check"],
      retained_checks:["endpoint_mcp_preflight","immutable_source","native_generation",
        "method_contract","proposal_review","training_receipt","merged_vllm_evaluation"]}' \
    > "${attempt}/metadata/lifecycle_proof_override.json"
  chmod 400 "${attempt}/metadata/lifecycle_proof_override.json"
fi
"${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_10/runtime/snapshot_vllm_runtime.sh" "${attempt}" \
  > "${attempt}/metadata/vllm_runtime_path.txt"

export PATH="/storage/home/${USER}/tools/node-v22.22.0-linux-arm64/bin:${PATH}"
export KIMI_CLI_PATH="/storage/home/${USER}/tools/kimi-code-2.1.1/node_modules/.bin/kimi"
export AAR_WEB_MODE=native_web
export AAR_KIMI_SERVE_DEPLOYMENT=autodata2_8-kimi26 AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT="/storage/home/${USER}/ram_common-gemma/vllm_tools/serve_api_v2"
export KIMI_MODEL_CAPABILITIES=tool_use KIMI_MODEL_MAX_CONTEXT_SIZE=262144
export KIMI_MODEL_MAX_OUTPUT_SIZE=65536 KIMI_MODEL_MAX_COMPLETION_TOKENS=65536
unset KIMI_AGENT_MODEL
PYTHONPATH="${SOURCE_REPO}" timeout 420 "${SHARED_HARNESS_PY}" \
  "${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_10/canary/verify_kimi_endpoint.py" \
  --workspace "${SOURCE_REPO}" --output "${attempt}/metadata/kimi_mcp_preflight.json" \
  --timeout-seconds "${AAR_KIMI_PREFLIGHT_TIMEOUT_SECONDS:-180}" \
  --cache-ttl-seconds "${AAR_KIMI_PREFLIGHT_CACHE_TTL_SECONDS:-21600}"

export AAR_REPO="${SOURCE_REPO}" AAR_SOURCE_SNAPSHOT="${SOURCE_REPO}"
export AAR_TRUSTED_HARNESS_PY="${SHARED_HARNESS_PY}"
export HARNESS_PY="${SHARED_HARNESS_PY}" HARNESS_ENV="${SECRET_ENV}"
export WORKSPACE_DIR="${SOURCE_REPO}" PYTHONPATH="${SOURCE_REPO}"
export AAR_BENCHMARK_DOCS="${SOURCE_REPO}/benchmark_docs"
export BENCHMARK_DOCS_DIR="${SOURCE_REPO}/benchmark_docs"
export AAR_RUN_CONFIG="${SNAPSHOT_RUN_CONFIG}"
export AAR_RUN_ATTEMPT_DIR="${attempt}" AAR_RUNTIME_ROOT="${attempt}"
export AAR_BASELINE_GIT_COMMIT="${commit}" AAR_REUSED_BASELINE="${SNAPSHOT_REUSED_BASELINE}"
export AAR_RECOVERED_BASELINE_SOURCES="${SNAPSHOT_RECOVERED_SOURCES}"
export AAR_MONITOR_MODEL_API_KEY="${MODEL_API_KEY}"
export AAR_RUN15_MODE="${MODE}"
export AAR_RUN15_LIFECYCLE_PROOF_POLICY="${LIFECYCLE_PROOF_POLICY}"
pipeline_time=02:00:00
[ "${MODE}" != canary ] || pipeline_time=04:00:00
job="$(sbatch --parsable --time="${pipeline_time}" \
  --output="${attempt}/logs/pipeline-%j.out" --export=ALL \
  "${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_15/slurm/pipeline.sbatch")"

submitted_at_pt="$(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z')"
source_snapshots_sha256="sha256:$(sha256sum "${attempt}/metadata/source-snapshots.json" | awk '{print $1}')"
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nsource_snapshot_root=%s\nsource_snapshots_sha256=%s\nmode=%s\nlifecycle_name=%s\nlifecycle_proof_policy=%s\nsubmitted_at_pt=%s\nresearch_backend=%s\nresearch_model=Kimi-K2.6\nresearcher_deployment=autodata2_8-kimi26\ndata_generation_backend=native\nautodata=0\nseeds=%s\ntarget_score_result_pairs=%s\n' \
  "${job}" "${attempt}" "${commit}" "${SOURCE_REPO}" \
  "${source_snapshots_sha256}" "${MODE}" "${AAR_LIFECYCLE_NAME:-none}" \
  "${LIFECYCLE_PROOF_POLICY}" "${submitted_at_pt}" "${AAR_AGENT_BACKEND}" "${AAR_RESEARCH_SEEDS}" \
  "${AAR_TARGET_SUCCESSFUL_ITERATIONS}" | tee "${attempt}/metadata/submission.txt"
unset MODEL_API_KEY HF_TOKEN
