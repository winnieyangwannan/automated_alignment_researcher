#!/bin/bash
# scripts/publish_holdout.sh — EVAL-side: publish the holdout suite for a given AXIS + MODEL
# and emit the research-readable per-model prompt baselines. RUN AS THE EVAL USER (it writes
# into the mode-700 holdout). It resolves axis + model from the SAME source the research side
# uses (axis_env.sh + models.sh), so the published baselines match the model the AAR optimizes.
#
#   AXIS=sycophancy MODEL=mistral scripts/publish_holdout.sh
#
# Per-model baselines come from benchmark_docs/<axis>/baseline.json — deploy that EVAL-side
# (mode-700; it names the held-out, so it must NOT be research-readable). If it's absent, the
# PUBLISHERS fallback (exact for qwen) is used with a loud WARN. The held-out is INCLUDED in
# the holdout suite (eval-only) but EXCLUDED from the research-readable prompt baselines.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
elif [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/aar" ]; then
  REPO="$(cd -- "${SLURM_SUBMIT_DIR}" && pwd)"
else
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
fi
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
PY="${AAR_PY:-${HARNESS_PY}}"
[ -x "${PY}" ] || { echo "[publish] ERROR: Python is not executable: ${PY}" >&2; exit 2; }
# The holdout lives in the eval user's mode-700 space (the same dir the eval worker reads).
# PER-MODEL by default: holdout/<model_tag>/<axis>. Two teams on the SAME axis but DIFFERENT models
# (e.g. sycophancy×phi and sycophancy×olmo) therefore get SEPARATE holdout dirs automatically and can
# NEVER clobber each other's per-model baselines — no manual namespacing. The eval worker derives the
# IDENTICAL <model_tag> from the team id (scripts/eval_worker.sh), so publish and score always agree.
# (Explicit HOLDOUT_DIR still wins.) model_tag = the sanitized MODEL alias/id.
_MTAG="$(printf '%s' "${MODEL:-qwen}" | tr -c 'A-Za-z0-9._-' '_')"
export HOLDOUT_DIR="${HOLDOUT_DIR:-${AAR_RUNTIME_ROOT}/eval/holdout/${_MTAG}}"
# benchmark_docs (the per-model baseline source, all 6 models) lives EVAL-side mode-700 —
# it names the held-out, so it must NOT be research-readable. publish_suite reads it via
# AAR_BENCHMARK_DOCS. If the dir is absent, it falls back to the qwen-only PUBLISHERS values
# with a loud WARN (so non-qwen baselines can't silently be wrong).
export AAR_BENCHMARK_DOCS="${AAR_BENCHMARK_DOCS:-${REPO}/benchmark_docs}"
# GATED datasets (e.g. walledai/HarmBench) need HF auth or publish_suite SILENTLY
# skips them — which drops a SAFETY benchmark from the suite (observed: OLMo's
# harmbench vanished, leaving 3 refusal benchmarks instead of 4, unequal to the
# other models). Source the token + cache from the eval .env (same as eval_worker.sh)
# so every refusal benchmark publishes. HARNESS still WARNs+skips if truly unavailable.
export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN:-}"
[ -n "${HF_TOKEN:-}" ] || { echo "[publish] ERROR: HF_TOKEN is required" >&2; exit 2; }
# shellcheck disable=SC1091
source "${REPO}/scripts/axis_env.sh"      # -> SUITE_NAME (from AXIS), TARGET_MODEL (from MODEL), BASELINES_PATH
export PYTHONPATH="${REPO}"
echo "[publish] axis=${SUITE_NAME}  model=${TARGET_MODEL}"
echo "[publish] holdout -> ${HOLDOUT_DIR}/${SUITE_NAME}/   baselines -> ${BASELINES_PATH}"

if [ -e "${HOLDOUT_DIR}/${SUITE_NAME}" ] && [ "${AAR_ALLOW_HOLDOUT_OVERWRITE:-0}" != "1" ]; then
  echo "[publish] ERROR: refusing to overwrite retained suite ${HOLDOUT_DIR}/${SUITE_NAME}" >&2
  echo "[publish] choose a fresh HOLDOUT_DIR or explicitly set AAR_ALLOW_HOLDOUT_OVERWRITE=1" >&2
  exit 2
fi
if [ -e "${BASELINES_PATH}" ] && [ "${AAR_ALLOW_HOLDOUT_OVERWRITE:-0}" != "1" ]; then
  echo "[publish] ERROR: refusing to overwrite retained prompt baselines ${BASELINES_PATH}" >&2
  echo "[publish] choose a fresh AAR_RUNTIME_ROOT or explicitly set AAR_ALLOW_HOLDOUT_OVERWRITE=1" >&2
  exit 2
fi

# 1) Holdout suite YAML + data (SECRET; includes the held-out) into the mode-700 holdout.
"${PY}" "${REPO}/scripts/publish_suite.py" \
    --suite "${SUITE_NAME}" --target-model "${TARGET_MODEL}" --holdout-dir "${HOLDOUT_DIR}"

# 2) Research-readable prompt baselines (held-out EXCLUDED), authoritative per-model.
mkdir -p "$(dirname "${BASELINES_PATH}")"
"${PY}" "${REPO}/scripts/publish_suite.py" \
    --emit-prompt-baselines "${BASELINES_PATH}" --suite "${SUITE_NAME}" --target-model "${TARGET_MODEL}"
# This file MUST be research-readable — the AAR (research user) reads it for its prompt baselines.
# The eval user's umask is 077, which would leave it mode-600 and the AAR would silently fall back
# to the 0.0 PUBLISHERS placeholders. Force it readable.
chmod 644 "${BASELINES_PATH}" 2>/dev/null || true

echo "[publish] done. Now run the worker:  AXIS=${AXIS:-sycophancy} MODEL=${MODEL:-qwen} scripts/launch_eval_worker.sh"
