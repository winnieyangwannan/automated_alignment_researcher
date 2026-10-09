#!/bin/bash
# Submit the no-evaluator method smoke, scored canary, or full Run 10 experiment.
set -euo pipefail
umask 077

MODE="${1:-canary}"
case "${MODE}" in smoke|canary|full) ;; *) echo "usage: $0 smoke|canary|full [canary-proof]" >&2; exit 2;; esac
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
RECOVERY_BUNDLE="${AAR_RUN10_RECOVERY_BUNDLE:-/storage/home/winnieyangwn/aar-recovery/run7_20261007T004406Z-1b3303d02821/baseline_salvage}"
RECOVERY_BUNDLE="$(realpath -e -- "${RECOVERY_BUNDLE}")"
REUSED_BASELINE="${RECOVERY_BUNDLE}/gemma4_31b_multidimensional_baseline.json"
RECOVERED_SOURCES="${RECOVERY_BUNDLE}/source_artifacts"
SECRET_ENV="$(realpath -e -- "${AAR_RUN10_SECRET_ENV:-${REPO}/.env}")"
KIMI_ROOT="${AAR_RUN10_KIMI_ROOT:-/storage/home/${USER:?}/tools/kimi-code-2.1.1}"
NODE_ROOT="${AAR_RUN10_NODE_ROOT:-/storage/home/${USER}/tools/node-v22.22.0-linux-arm64}"
EXPECTED_BRANCH="${AAR_EXPECTED_BRANCH:-multi_kimi}"
KIMI_DEPLOYMENT="${AAR_KIMI_SERVE_DEPLOYMENT:-steerability_8-kimi26}"
CANARY_ITERATIONS="${AAR_RUN10_CANARY_ITERATIONS:-1}"
RECOVERED_AGENT_LOG_DIR="${AAR_RUN10_RECOVERED_AGENT_LOG_DIR:-}"

[ "$(git -C "${REPO}" branch --show-current)" = "${EXPECTED_BRANCH}" ] || {
  echo "Run 10 requires branch ${EXPECTED_BRANCH}" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi
[ -z "$(git -C "${REPO}" status --porcelain --untracked-files=all -- aar benchmark_docs scripts replication pyproject.toml uv.lock "${SCRIPT_DIR}")" ] || {
  echo "launch-critical files are dirty" >&2; exit 2;
}
[ -x "${REPO}/.venv/bin/python" ] || { echo "missing worktree-local ARM64 .venv" >&2; exit 2; }
"${REPO}/.venv/bin/python" -c 'import platform; assert platform.machine() == "aarch64"'
[ -x "${KIMI_ROOT}/node_modules/.bin/kimi" ] || { echo "pinned Kimi runtime is missing" >&2; exit 2; }
[ "$("${NODE_ROOT}/bin/node" --version)" = v22.22.0 ] || { echo "pinned Node runtime is missing" >&2; exit 2; }
case "${CANARY_ITERATIONS}" in
  ''|*[!0-9]*) echo "canary iterations must be an integer" >&2; exit 2 ;;
esac
[ "${CANARY_ITERATIONS}" -ge 1 ] && [ "${CANARY_ITERATIONS}" -le 5 ] || {
  echo "canary iterations must be between 1 and 5" >&2
  exit 2
}
if [ -n "${RECOVERED_AGENT_LOG_DIR}" ]; then
  [ "${MODE}" = canary ] || { echo "recovered agent memory is canary-only" >&2; exit 2; }
  RECOVERED_AGENT_LOG_DIR="$(realpath -e -- "${RECOVERED_AGENT_LOG_DIR}")"
  [ -f "${RECOVERED_AGENT_LOG_DIR}/AGENT_LOG_gemma4_31b_explore_canary.md" ] || {
    echo "recovered Run 10 agent log is missing" >&2
    exit 2
  }
fi

CANARY_PROOF=""
if [ "${MODE}" = full ]; then
  CANARY_PROOF="$(realpath -e -- "${2:?full launch requires canary_passed.json}")"
  [ "$(jq -r '.status' "${CANARY_PROOF}")" = passed ] || { echo "canary proof is not passed" >&2; exit 2; }
  for field in score_result_pair fail_closed_markers merge_manifest_retained ephemeral_merge_removed kimi_mcp_tool_roundtrip method_gpu_smoke adapter_reload_validation on_demand_evaluator; do
    [ "$(jq -r --arg field "${field}" '.[$field]' "${CANARY_PROOF}")" = true ] || { echo "canary did not prove ${field}" >&2; exit 2; }
  done
  git -C "${REPO}" merge-base --is-ancestor "$(jq -r '.canary_git_commit' "${CANARY_PROOF}")" HEAD || {
    echo "current commit does not descend from canary commit" >&2; exit 2;
  }
fi

source_root="${REPO}/data/LLM-Uncertainty-Bench"
"${REPO}/.venv/bin/python" "${REPO}/scripts/prepare_llm_uncertainty_source.py" --output-root "${source_root}" --verify-only >/dev/null
export LLM_UNCERTAINTY_SRC="${source_root}/data"
export LLM_UNCERTAINTY_SOURCE_MANIFEST="${source_root}/.aar-source.json"
export AAR_REPO="${REPO}" HARNESS_ENV="${SECRET_ENV}"
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
for secret_name in HF_TOKEN MODEL_API_KEY; do
  [ -n "${!secret_name:-}" ] || { echo "Run 10 requires ${secret_name}" >&2; exit 2; }
done
"${REPO}/.venv/bin/python" "${REPO}/scripts/validate_reused_multidimensional_baseline.py" \
  "${REUSED_BASELINE}" --recovered-source-dir "${RECOVERED_SOURCES}" >/dev/null

commit="$(git -C "${REPO}" rev-parse HEAD)"
attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "${REPO}" rev-parse --short=12 HEAD)"
attempt_parent="${AAR_RUN10_ATTEMPT_PARENT:-/storage/home/${USER}/aar-runs/run10_kimi/${MODE}_attempts}"
attempt_dir="${attempt_parent}/${attempt_id}"
mkdir -p "${attempt_parent}"
mkdir "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
chmod 700 "${attempt_dir}" "${attempt_dir}/metadata" "${attempt_dir}/logs"
recovered_agent_log_for_launch=""
if [ -n "${RECOVERED_AGENT_LOG_DIR}" ]; then
  recovered_agent_log_for_launch="${attempt_dir}/metadata/recovered-agent-log"
  mkdir "${recovered_agent_log_for_launch}"
  chmod 700 "${recovered_agent_log_for_launch}"
  cp -- "${RECOVERED_AGENT_LOG_DIR}/AGENT_LOG_gemma4_31b_explore_canary.md" \
    "${recovered_agent_log_for_launch}/AGENT_LOG_gemma4_31b_explore_canary.md"
  chmod 600 "${recovered_agent_log_for_launch}/AGENT_LOG_gemma4_31b_explore_canary.md"
fi
[ -z "${CANARY_PROOF}" ] || cp -- "${CANARY_PROOF}" "${attempt_dir}/metadata/canary_passed.json"
"${SCRIPT_DIR}/snapshot_vllm_runtime.sh" "${attempt_dir}" > "${attempt_dir}/metadata/vllm_runtime_path.txt"
printf 'export AAR_RUNTIME_ROOT=%q\n' "${attempt_dir}" > "${attempt_dir}/attempt.env"

export PATH="${NODE_ROOT}/bin:${PATH}"
export KIMI_CLI_PATH="${KIMI_ROOT}/node_modules/.bin/kimi"
export AAR_AGENT_BACKEND=kimi AAR_WEB_MODE=native_web
export AAR_EXPECTED_BRANCH="${EXPECTED_BRANCH}"
export AAR_KIMI_SERVE_DEPLOYMENT="${KIMI_DEPLOYMENT}" AAR_KIMI_EXPECTED_MODEL=Kimi-K2.6
export AAR_KIMI_PROVIDER_TYPE=kimi AAR_KIMI_DISABLE_THINKING=1
export AAR_SERVE_API_V2_ROOT="/storage/home/${USER}/ram_common/vllm_tools/serve_api_v2"
export KIMI_MODEL_CAPABILITIES=tool_use
export AAR_KIMI_MCP_MAX_TEXT_CHARS=16000
unset KIMI_AGENT_MODEL
if [ "${MODE}" = smoke ]; then
  _cpu_gate_env=(env -i \
    HOME="${HOME}" USER="${USER}" LOGNAME="${LOGNAME:-${USER}}" \
    PATH="${PATH}" PYTHONPATH="${REPO}" LANG="${LANG:-C.UTF-8}")
  "${_cpu_gate_env[@]}" "${REPO}/.venv/bin/python" -m pytest -q \
    "${REPO}/tests/test_kimi_agent.py" \
    "${REPO}/tests/test_full_loop_launch.py" \
    "${REPO}/tests/test_validate_method_contract.py" \
    > "${attempt_dir}/metadata/cpu_replay_gate.txt"
  "${_cpu_gate_env[@]}" "${REPO}/.venv/bin/ruff" check \
    "${REPO}/aar/research_loop/kimi_agent.py" \
    "${REPO}/scripts/validate_method_contract.py" \
    >> "${attempt_dir}/metadata/cpu_replay_gate.txt"
fi
"${REPO}/.venv/bin/python" "${SCRIPT_DIR}/verify_kimi_endpoint.py" \
  --workspace "${REPO}" --output "${attempt_dir}/metadata/kimi_mcp_preflight.json"

export AAR_RUNTIME_ROOT="${attempt_dir}" AAR_RUN_ATTEMPT_DIR="${attempt_dir}"
export AAR_BASELINE_GIT_COMMIT="${commit}" AAR_REUSED_BASELINE="${REUSED_BASELINE}"
export AAR_RECOVERED_BASELINE_SOURCES="${RECOVERED_SOURCES}" AAR_RUN10_MODE="${MODE}"
export AAR_RUN10_CANARY_ITERATIONS="${CANARY_ITERATIONS}"
if [ -n "${recovered_agent_log_for_launch}" ]; then
  export AAR_RECOVERED_AGENT_LOG_DIR="${recovered_agent_log_for_launch}"
fi
job_id="$(sbatch --parsable --account=ram --partition=g3 --qos=g3_ram_high \
  --cpus-per-task=16 --mem=128G --time=02:00:00 \
  --job-name="aar-run10-kimi-${MODE}-launch" --output="${attempt_dir}/logs/pipeline-%j.out" \
  --export=ALL "${SCRIPT_DIR}/run_10_pipeline.sbatch")"
research_chains=1; max_iterations=1; evaluator_jobs=1; evaluator_gpus=4
if [ "${MODE}" = full ]; then
  research_chains=5; max_iterations=50; evaluator_jobs=5
elif [ "${MODE}" = canary ]; then
  max_iterations="${CANARY_ITERATIONS}"
elif [ "${MODE}" = smoke ]; then
  evaluator_jobs=0; evaluator_gpus=0
fi
printf 'launch_job_id=%s\nattempt_dir=%s\ngit_commit=%s\nmode=%s\nresearch_backend=kimi\nresearch_model=Kimi-K2.6\ndeployment=%s\nresearch_chains=%s\nmax_iterations_per_chain=%s\nevaluator_jobs=%s\nevaluator_gpus_per_job=%s\nrecovered_agent_log_dir=%s\n' \
  "${job_id}" "${attempt_dir}" "${commit}" "${MODE}" "${KIMI_DEPLOYMENT}" \
  "${research_chains}" "${max_iterations}" "${evaluator_jobs}" "${evaluator_gpus}" \
  "${recovered_agent_log_for_launch:-none}" | tee "${attempt_dir}/metadata/submission.txt"
