#!/bin/bash
# Submit Run 16: Run 15 topology with Claude Opus 4.8 research.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN16_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO="$(cd -- "${RUN16_DIR}/../../.." && pwd)"
CANONICAL_CONFIG="$(realpath -e -- "${RUN16_DIR}/config/run.yaml")"
RUN_CONFIG="$(realpath -e -- "${AAR_RUN_CONFIG:-${CANONICAL_CONFIG}}")"
MODE="${AAR_RUN16_MODE:-full}"
case "${MODE}" in full|canary) ;; *) echo "AAR_RUN16_MODE must be full or canary" >&2; exit 2;; esac
[ "${MODE}" != full ] || [ "${RUN_CONFIG}" = "${CANONICAL_CONFIG}" ] || {
  echo "Run 16 full mode requires the canonical run YAML" >&2
  exit 2
}
if [ "${MODE}" = full ]; then
  [ "$#" -eq 2 ] || {
    echo "usage: $0 <one-chain-proof.json> <five-chain-proof.json>" >&2
    exit 2
  }
  ONE_CHAIN_PROOF="$(realpath -e -- "$1")"
  FIVE_CHAIN_PROOF="$(realpath -e -- "$2")"
else
  [ "$#" -eq 0 ] || {
    echo "Run 16 canary mode takes no positional arguments" >&2
    exit 2
  }
  ONE_CHAIN_PROOF=""
  FIVE_CHAIN_PROOF=""
fi

[ -x "${REPO}/.venv/bin/python" ] || { echo "missing worktree-local runtime" >&2; exit 2; }
SHARED_HARNESS_PY="${REPO}/.venv/bin/python"
SECRET_ENV="$(realpath -e -- "${AAR_RUN16_SECRET_ENV:-${REPO}/.env}")"
RECOVERY_BUNDLE="$(realpath -e -- "${AAR_RUN16_RECOVERY_BUNDLE:-/storage/home/${USER:?}/aar-recovery/run7_20261007T004406Z-1b3303d02821/baseline_salvage}")"
REUSED_BASELINE="${RECOVERY_BUNDLE}/gemma4_31b_multidimensional_baseline.json"
RECOVERED_SOURCES="${RECOVERY_BUNDLE}/source_artifacts"

export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}" AAR_RUN_CONFIG="${RUN_CONFIG}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/replication/env_multidimensional.sh"
eval "$("${REPO}/.venv/bin/python" "${REPO}/scripts/load_aar_run_config.py" "${RUN_CONFIG}")"
[ "${AAR_AUTODATA:?missing data-generation backend}" = 0 ] || {
  echo "Run 16 requires data_generation.backend=native" >&2
  exit 2
}
while IFS= read -r name; do unset "${name}"; done < <(compgen -A variable AAR_AUTODATA_)
export AAR_AUTODATA=0
commit="$(git -C "${REPO}" rev-parse HEAD)"

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
    ephemeral_merge_removed claude_research_preflight method_gpu_smoke \
    adapter_reload_validation on_demand_evaluator evaluation_item_contract \
    autodata_disabled immutable_source source_commit_consistent; do
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
    "${AAR_RUN16_PREREQUISITE_PROOF:?five-chain canary requires the one-chain proof}")"
  validate_lifecycle_proof \
    "${PREREQUISITE_PROOF}" "${AAR_LIFECYCLE_PREREQUISITE_CHAIN_COUNT}"
fi
if [ "${MODE}" = full ]; then
  validate_lifecycle_proof "${ONE_CHAIN_PROOF}" 1
  validate_lifecycle_proof "${FIVE_CHAIN_PROOF}" 5
  one_chain_proof_sha256="$(sha256sum -- "${ONE_CHAIN_PROOF}" | awk '{print $1}')"
  [ "$(jq -r '.prerequisite_proof_sha256 // empty' "${FIVE_CHAIN_PROOF}")" = \
    "${one_chain_proof_sha256}" ] || {
    echo "five-chain proof is not bound to the supplied one-chain proof" >&2
    exit 2
  }
fi

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 16 requires branch autodata" >&2
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
  [ -n "${!secret_name:-}" ] || { echo "Run 16 requires ${secret_name}" >&2; exit 2; }
done

storage_root="${AAR_RUN_STORAGE_ROOT:?run config did not set storage.root}"
case "${storage_root}" in /checkpoint/ram/aar/"${USER}"/run16_native_generation) ;; *)
  echo "unexpected Run 16 storage root: ${storage_root}" >&2; exit 2;;
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
[ -x "${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_16/launch/submit_full.sh" ] || {
  echo "Run 16 launcher is absent from the source commit" >&2
  exit 2
}
case "${RUN_CONFIG}" in
  "${REPO}"/*)
    SNAPSHOT_RUN_CONFIG="${SOURCE_REPO}/${RUN_CONFIG#"${REPO}/"}"
    ;;
  *)
    echo "Run 16 config must be tracked inside the source repository" >&2
    exit 2
    ;;
esac
[ -s "${SNAPSHOT_RUN_CONFIG}" ] || {
  echo "attempt-local Run 16 config is missing" >&2
  exit 2
}
cmp -s -- "${RUN_CONFIG}" "${SNAPSHOT_RUN_CONFIG}" || {
  echo "attempt-local Run 16 config differs from the validated config" >&2
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
if [ "${MODE}" = full ]; then
  cp -- "${ONE_CHAIN_PROOF}" \
    "${attempt}/metadata/one_chain_lifecycle_passed.json"
  cp -- "${FIVE_CHAIN_PROOF}" \
    "${attempt}/metadata/five_chain_lifecycle_passed.json"
  five_chain_proof_sha256="$(sha256sum -- "${FIVE_CHAIN_PROOF}" | awk '{print $1}')"
  printf 'one_chain_sha256=%s\nfive_chain_sha256=%s\n' \
    "${one_chain_proof_sha256}" "${five_chain_proof_sha256}" \
    > "${attempt}/metadata/lifecycle_proofs.sha256"
fi
"${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_10/runtime/snapshot_vllm_runtime.sh" "${attempt}" \
  > "${attempt}/metadata/vllm_runtime_path.txt"

export AAR_AGENT_MODEL=claude-opus-4-8 AAR_EFFORT=max AAR_WEB_MODE=meta_secure
CLAUDE_CLI_PATH="${CLAUDE_CLI_PATH:-$(command -v claude || true)}"
export CLAUDE_CLI_PATH
[ -x "${CLAUDE_CLI_PATH}" ] || { echo "Claude CLI is missing" >&2; exit 2; }
"${CLAUDE_CLI_PATH}" --help 2>&1 | grep -q -- --secure-internet-mode || {
  echo "Claude CLI lacks secure-internet mode" >&2
  exit 2
}
[ -x "${SOURCE_REPO}/scripts/aar-paper-search" ] || {
  echo "bounded paper-search helper is missing" >&2
  exit 2
}
"${SHARED_HARNESS_PY}" - \
  "${attempt}/metadata/claude_research_preflight.json" \
  "${CLAUDE_CLI_PATH}" <<'PY'
import json
import pathlib
import sys

output = pathlib.Path(sys.argv[1])
output.write_text(
    json.dumps(
        {
            "schema": "aar.claude-research-preflight/v1",
            "status": "passed",
            "research_backend": "claude",
            "research_model": "claude-opus-4-8",
            "research_effort": "max",
            "claude_cli_path": sys.argv[2],
            "claude_cli_executable": True,
            "secure_internet_mode": True,
            "bounded_paper_search": True,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

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
export AAR_RUN16_MODE="${MODE}"
pipeline_time=02:00:00
[ "${MODE}" != canary ] || pipeline_time=04:00:00
job="$(sbatch --parsable --time="${pipeline_time}" \
  --output="${attempt}/logs/pipeline-%j.out" --export=ALL \
  "${SOURCE_REPO}/experiments/dishonest_sycophancy_concealing/run_16/slurm/pipeline.sbatch")"

submitted_at_pt="$(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z')"
source_snapshots_sha256="sha256:$(sha256sum "${attempt}/metadata/source-snapshots.json" | awk '{print $1}')"
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nsource_snapshot_root=%s\nsource_snapshots_sha256=%s\nmode=%s\nlifecycle_name=%s\nsubmitted_at_pt=%s\nresearch_backend=%s\nresearch_model=%s\nresearch_effort=%s\ndata_generation_backend=native\nautodata=0\nseeds=%s\ntarget_score_result_pairs=%s\n' \
  "${job}" "${attempt}" "${commit}" "${SOURCE_REPO}" \
  "${source_snapshots_sha256}" "${MODE}" "${AAR_LIFECYCLE_NAME:-none}" \
  "${submitted_at_pt}" "${AAR_AGENT_BACKEND}" "${AAR_AGENT_MODEL}" \
  "${AAR_EFFORT}" "${AAR_RESEARCH_SEEDS}" \
  "${AAR_TARGET_SUCCESSFUL_ITERATIONS}" | tee "${attempt}/metadata/submission.txt"
unset MODEL_API_KEY HF_TOKEN
