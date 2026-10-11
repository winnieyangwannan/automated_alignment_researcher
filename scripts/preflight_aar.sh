#!/bin/bash
# Non-mutating preflight for the FAIR honesty AAR loop. It reads configuration
# and validates the runtime; it never publishes, purges, moves, submits, or
# deletes data. Run once on the login node and once inside a GPU allocation.

set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
else
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
fi
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"

pass() { echo "[preflight] PASS: $*"; }
fail() { echo "[preflight] FAIL: $*" >&2; exit 1; }

if [ -n "${AAR_EXPECTED_COMMIT:-}" ]; then
  [ -z "$(git -C "${REPO}" branch --show-current)" ] || \
    fail "commit-pinned source snapshot is not detached"
  [ "$(git -C "${REPO}" rev-parse HEAD)" = "${AAR_EXPECTED_COMMIT}" ] || \
    fail "source snapshot does not match AAR_EXPECTED_COMMIT"
  pass "detached source snapshot at $(git -C "${REPO}" rev-parse --short HEAD)"
else
  _EXPECTED_BRANCH="${AAR_EXPECTED_BRANCH:-uv}"
  [ "$(git -C "${REPO}" branch --show-current)" = "${_EXPECTED_BRANCH}" ] || \
    fail "checkout is not on branch ${_EXPECTED_BRANCH}"
  pass "branch ${_EXPECTED_BRANCH} at $(git -C "${REPO}" rev-parse --short HEAD)"
fi
[ -x "${HARNESS_PY}" ] || fail "Python is not executable: ${HARNESS_PY}"
pass "Python ${HARNESS_PY}"
case "${SUITE_NAME}" in
  honesty)
    [ "${TARGET_MODEL}" = google/gemma-2-2b-it ] || fail "expected Gemma-2 target, got ${TARGET_MODEL}"
    [ "${HELD_OUT_BENCH}" = deceptionbench_reward ] || fail "unexpected honesty held-out id"
    ;;
  honesty_sycophancy)
    [ "${TARGET_MODEL}" = google/gemma-4-31B-it ] || fail "expected Gemma-4-31B target, got ${TARGET_MODEL}"
    [ "${HELD_OUT_BENCH}" = deceptionbench_reward,sycon_fp ] || fail "unexpected composed held-out ids"
    [ "${EVAL_RUN_BATCH:-}" = 2 ] || fail "composed suite requires EVAL_RUN_BATCH=2"
    [ "${EVAL_RUN_GEN_CEILING:-}" = 8192 ] || fail "composed suite requires the 8192-token generation ceiling"
    [ "${EVAL_FAIL_ON_ALLOCATOR_WARNING:-}" = 1 ] || fail "allocator-warning gate is disabled"
    [ "${EVAL_MAX_TRUNCATION_RATE:-}" = 0.05 ] || fail "truncation gate must be 0.05"
    [ -s "${AAR_BASELINE_OVERRIDES:-}" ] || fail "combined baseline override is missing"
    [ -s "${HOLDOUT_DIR:-}/honesty_sycophancy/honesty_sycophancy.yaml" ] || fail "combined suite YAML is missing"
    [ "${AAR_MULTIDIM_SCORING_CONFIRMED:-}" = 1 ] || fail "multi-dimensional scoring decision is not confirmed"
    ;;
  honesty_sycophancy_concealing_uncertainty)
    [ "${TARGET_MODEL}" = google/gemma-4-31B-it ] || fail "expected Gemma-4-31B target, got ${TARGET_MODEL}"
    [ "${HELD_OUT_BENCH}" = deceptionbench_reward,sycon_fp,sciq_uncertainty ] || fail "unexpected three-dimension held-out ids"
    [ "${EVAL_RUN_BATCH:-}" = 2 ] || fail "composed suite requires EVAL_RUN_BATCH=2"
    [ "${EVAL_RUN_GEN_CEILING:-}" = 8192 ] || fail "composed suite requires the 8192-token generation ceiling"
    [ "${EVAL_REQUIRE_EXACT_MAX_NEW_TOKENS:-}" = 1 ] || fail "exact generation-budget contract is disabled"
    [ "${EVAL_FAIL_ON_ALLOCATOR_WARNING:-}" = 1 ] || fail "allocator-warning gate is disabled"
    [ "${EVAL_MAX_TRUNCATION_RATE:-}" = 0.10 ] || fail "truncation gate must be 0.10"
    [ -s "${AAR_BASELINE_OVERRIDES:-}" ] || fail "combined baseline override is missing"
    [ -s "${HOLDOUT_DIR:-}/${SUITE_NAME}/${SUITE_NAME}.yaml" ] || fail "combined suite YAML is missing"
    [ "${AAR_MULTIDIM_SCORING_CONFIRMED:-}" = 1 ] || fail "multi-dimensional scoring decision is not confirmed"
    ;;
  *) fail "unsupported suite ${SUITE_NAME}" ;;
esac
pass "axis/model contract: ${SUITE_NAME} / ${TARGET_MODEL}"

MONITOR_BACKEND="${AAR_MONITOR_BACKEND:-model_api}"
JUDGE_BACKEND="${JUDGE_BACKEND:-model_api}"
AGENT_BACKEND="${AAR_AGENT_BACKEND:-claude}"
case "${AGENT_BACKEND}" in
  claude)
    CLI="${CLAUDE_CLI_PATH:-$(command -v claude || true)}"
    [ -x "${CLI:-}" ] || fail "Claude CLI is missing"
    "${CLI}" --help 2>&1 | grep -q -- '--secure-internet-mode' || fail "Claude CLI lacks secure-internet support"
    [ -x "${REPO}/scripts/aar-paper-search" ] || fail "bounded paper-search helper is missing"
    [ "${AAR_AGENT_MODEL:-claude-opus-4-8}" = claude-opus-4-8 ] || fail "research agent must use claude-opus-4-8"
    pass "Meta Claude CLI and bounded paper search; model=claude-opus-4-8"
    ;;
  kimi)
    CLI="${KIMI_CLI_PATH:-$(command -v kimi || true)}"
    [ -x "${CLI:-}" ] || fail "Kimi CLI is missing"
    _KIMI_HELP="$("${CLI}" --help 2>&1 || true)"
    case "${_KIMI_HELP}" in *--prompt*--output-format*) ;; *) fail "Kimi CLI lacks structured prompt mode";; esac
    unset _KIMI_HELP
    pass "Kimi CLI structured prompt mode; model=${KIMI_AGENT_MODEL:-configured default}"
    ;;
  *) fail "unsupported AAR_AGENT_BACKEND=${AGENT_BACKEND}";;
esac
case "${MONITOR_BACKEND}" in
  model_api)
    [ -n "${MODEL_API_KEY:-}" ] || fail "MODEL_API_KEY is missing for monitor"
    [ "${MONITOR_MODEL:-claude-4-8-opus}" = claude-4-8-opus ] || fail "monitor must use claude-4-8-opus"
    ;;
  anthropic) [ -n "${ANTHROPIC_API_KEY:-${ANT_high_prio_API:-${ANT_API_KEY:-}}}" ] || fail "direct Anthropic key is missing for monitor";;
  *) fail "unsupported AAR_MONITOR_BACKEND=${MONITOR_BACKEND}";;
esac
case "${JUDGE_BACKEND}" in
  model_api)
    [ -n "${MODEL_API_KEY:-}" ] || fail "MODEL_API_KEY is missing for judge"
    if [ "${SUITE_NAME}" = honesty_sycophancy ] || [ "${SUITE_NAME}" = honesty_sycophancy_concealing_uncertainty ]; then
      [ "${JUDGE_MODEL:-}" = gpt-5-6-luna ] || fail "judge must use gpt-5-6-luna"
      [ "${MASK_JUDGE_MODEL:-}" = gpt-5-6-luna ] || fail "MASK judge must use gpt-5-6-luna"
    else
      [ "${JUDGE_MODEL:-claude-4-8-opus}" = claude-4-8-opus ] || fail "judge must use claude-4-8-opus"
      [ "${MASK_JUDGE_MODEL:-claude-4-8-opus}" = claude-4-8-opus ] || fail "MASK judge must use claude-4-8-opus"
    fi
    ;;
  anthropic) [ -n "${ANTHROPIC_API_KEY:-${ANT_high_prio_API:-${ANT_API_KEY:-}}}" ] || fail "direct Anthropic key is missing for judge";;
  *) fail "honesty preflight requires model_api or anthropic judge";;
esac
[ -n "${HF_TOKEN:-}" ] || fail "HF_TOKEN is missing"
pass "required credential variables are present (values hidden); monitor=${MONITOR_BACKEND} judge=${JUDGE_BACKEND}"

LIT_DIR="${LIT_AXIS_DIR:-${REPO}/_runs/litreview/${SUITE_NAME}}"
LIT_COUNT="$(LIT_AXIS_DIR="${LIT_DIR}" "${HARNESS_PY}" - <<'PY'
from aar.research_loop.tools.lit_forum import count
print(count())
PY
)"
[ "${LIT_COUNT}" -ge "${LITREVIEW_MIN:-30}" ] || fail "only ${LIT_COUNT} valid literature entries"
if [ "${SUITE_NAME}" = honesty_sycophancy ] || [ "${SUITE_NAME}" = honesty_sycophancy_concealing_uncertainty ]; then
  LIT_AXIS_DIR="${LIT_DIR}" "${HARNESS_PY}" - <<'PY'
import os
from aar.research_loop.tools.lit_forum import baseline_ready
minimum = int(os.getenv("LITREVIEW_MIN", "30"))
if not baseline_ready(minimum):
    raise SystemExit("literature manifest or per-track coverage is not ready")
PY
fi
pass "${LIT_COUNT} valid ${SUITE_NAME} literature entries"

if [ "${SUITE_NAME}" = honesty_sycophancy ] || [ "${SUITE_NAME}" = honesty_sycophancy_concealing_uncertainty ]; then
  "${HARNESS_PY}" - "${HOLDOUT_DIR}/${SUITE_NAME}/${SUITE_NAME}.yaml" <<'PY'
import sys
from aar.eval_pod.run_eval import load_suite_spec

suite, specs = load_suite_spec(sys.argv[1])
expected_by_suite = {
    "honesty_sycophancy": [
        "mask_factual", "mask_continuation", "mask_disinformation",
        "sycophancy_eval", "deceptionbench_reward", "sycon_fp",
        "mmlu", "gsm8k", "ifeval",
    ],
    "honesty_sycophancy_concealing_uncertainty": [
        "mask_factual", "mask_continuation", "mask_disinformation",
        "sycophancy_eval", "llm_uncertainty_bench", "verbalized_ece",
        "abstentionbench", "deceptionbench_reward", "sycon_fp",
        "sciq_uncertainty", "mmlu", "gsm8k", "ifeval",
    ],
}
expected = expected_by_suite[suite.name]
assert suite.aggregation == "coverage_weighted_geometric_mean"
assert suite.safety_regression_gate
assert [spec.name for spec in specs] == expected
assert all(spec.baseline_group for spec in specs)
print(f"[preflight] PASS: exact validated {len(expected)}-entry composed suite")
PY
fi

command -v sbatch >/dev/null || fail "sbatch is unavailable"
command -v sinfo >/dev/null || fail "sinfo is unavailable"
sinfo -h -p "${AAR_SLURM_PARTITION}" >/dev/null 2>&1 || fail "partition ${AAR_SLURM_PARTITION} is unavailable"
if command -v sacctmgr >/dev/null; then
  sacctmgr -nP show assoc user="${USER}" format=Account,QOS 2>/dev/null \
    | grep -Fq "${AAR_SLURM_ACCOUNT}" || fail "no Slurm association for account ${AAR_SLURM_ACCOUNT}"
fi
pass "Slurm account=${AAR_SLURM_ACCOUNT} partition=${AAR_SLURM_PARTITION} qos=${AAR_AGENT_QOS}/${AAR_TRAIN_QOS}/${AAR_EVAL_QOS}"

if [ -n "${SLURM_JOB_ID:-}" ] && [ -n "${CUDA_VISIBLE_DEVICES:-}" ]; then
  "${HARNESS_PY}" - <<'PY'
import platform
import torch
import transformers
import peft
import trl
import claude_agent_sdk

assert platform.machine() == "aarch64", platform.machine()
assert torch.version.cuda, "PyTorch is not CUDA-enabled"
assert torch.cuda.is_available(), "torch.cuda.is_available() is false"
x = torch.ones((64, 64), device="cuda", dtype=torch.bfloat16)
y = x @ x
assert float(y[0, 0]) == 64.0
print(f"[preflight] PASS: CUDA {torch.version.cuda}, {torch.cuda.get_device_name(0)}, BF16 matmul")
PY
else
  echo "[preflight] DEFER: GPU checks require a Slurm GPU allocation"
fi

echo "[preflight] PASS: non-mutating checks complete"
