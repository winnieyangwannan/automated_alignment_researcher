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

[ "$(git -C "${REPO}" branch --show-current)" = uv ] || fail "checkout is not on branch uv"
pass "branch uv at $(git -C "${REPO}" rev-parse --short HEAD)"
[ -x "${HARNESS_PY}" ] || fail "Python is not executable: ${HARNESS_PY}"
pass "Python ${HARNESS_PY}"
[ "${SUITE_NAME}" = honesty ] || fail "expected honesty suite, got ${SUITE_NAME}"
[ "${TARGET_MODEL}" = google/gemma-2-2b-it ] || fail "expected Gemma target, got ${TARGET_MODEL}"
[ "${HELD_OUT_BENCH}" = deceptionbench_reward ] || fail "unexpected honesty held-out id"
pass "axis/model contract: ${SUITE_NAME} / ${TARGET_MODEL}"

CLI="${CLAUDE_CLI_PATH:-$(command -v claude || true)}"
[ -x "${CLI:-}" ] || fail "Claude CLI is missing"
"${CLI}" --help 2>&1 | grep -q -- '--secure-internet-mode' || fail "Claude CLI lacks secure-internet support"
[ -x "${REPO}/scripts/aar-paper-search" ] || fail "bounded paper-search helper is missing"
pass "Meta Claude CLI and bounded paper search"

MONITOR_BACKEND="${AAR_MONITOR_BACKEND:-model_api}"
JUDGE_BACKEND="${JUDGE_BACKEND:-model_api}"
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
    [ "${JUDGE_MODEL:-claude-4-8-opus}" = claude-4-8-opus ] || fail "judge must use claude-4-8-opus"
    [ "${MASK_JUDGE_MODEL:-claude-4-8-opus}" = claude-4-8-opus ] || fail "MASK judge must use claude-4-8-opus"
    ;;
  anthropic) [ -n "${ANTHROPIC_API_KEY:-${ANT_high_prio_API:-${ANT_API_KEY:-}}}" ] || fail "direct Anthropic key is missing for judge";;
  *) fail "honesty preflight requires model_api or anthropic judge";;
esac
[ -n "${HF_TOKEN:-}" ] || fail "HF_TOKEN is missing"
pass "required credential variables are present (values hidden); monitor=${MONITOR_BACKEND} judge=${JUDGE_BACKEND}"

LIT_DIR="${LIT_AXIS_DIR:-${REPO}/_runs/litreview/${SUITE_NAME}}"
LIT_COUNT="$("${HARNESS_PY}" - "${LIT_DIR}" <<'PY'
import json
import pathlib
import sys

paths = sorted(pathlib.Path(sys.argv[1]).glob("*.json"))
for path in paths:
    with path.open() as handle:
        json.load(handle)
print(len(paths))
PY
)"
[ "${LIT_COUNT}" -ge "${LITREVIEW_MIN:-30}" ] || fail "only ${LIT_COUNT} valid literature entries"
pass "${LIT_COUNT} valid honesty literature entries"

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
