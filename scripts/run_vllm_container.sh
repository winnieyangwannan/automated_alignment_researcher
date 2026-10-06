#!/bin/bash
# Run one evaluator command in the exact vLLM image validated on FAIR GB300.
set -euo pipefail

[ "$#" -ge 1 ] || { echo "usage: $0 <command> [args...]" >&2; exit 2; }
: "${AAR_VLLM_CONTAINER_IMAGE:?missing AAR_VLLM_CONTAINER_IMAGE}"
: "${AAR_VLLM_WORKER_SH:?missing AAR_VLLM_WORKER_SH}"
: "${AAR_VLLM_CONTAINER_RW_MOUNT:?missing AAR_VLLM_CONTAINER_RW_MOUNT}"
: "${AAR_REPO:?missing AAR_REPO}"
: "${MODEL_CFG_PATH:?missing MODEL_CFG_PATH}"

case "${AAR_VLLM_CONTAINER_IMAGE}" in
  docker.io/vllm/vllm-openai:v0.25.1) ;;
  *) echo "refusing unvalidated vLLM image: ${AAR_VLLM_CONTAINER_IMAGE}" >&2; exit 2 ;;
esac
[ -r "${AAR_VLLM_WORKER_SH}" ] || {
  echo "vLLM container worker is unreadable: ${AAR_VLLM_WORKER_SH}" >&2
  exit 2
}
[ -d "${AAR_VLLM_CONTAINER_RW_MOUNT}" ] || {
  echo "container writable mount is missing: ${AAR_VLLM_CONTAINER_RW_MOUNT}" >&2
  exit 2
}

# shellcheck disable=SC1090
source "${AAR_VLLM_WORKER_SH}"
declare -f container_run >/dev/null || {
  echo "worker did not define container_run" >&2
  exit 2
}

# Extend the proven serve_api_v2 mount builder narrowly: its stock interface
# mounts the repository and model read-only, while the evaluator must atomically
# write scores below its own runtime root.
eval "$(declare -f _container_mount_args | sed '1s/_container_mount_args/_aar_base_container_mount_args/')"
_container_mount_args() {
  local -n _aar_mount_out="$1"
  _aar_base_container_mount_args "$1"
  _aar_mount_out+=(-v "${AAR_VLLM_CONTAINER_RW_MOUNT}:${AAR_VLLM_CONTAINER_RW_MOUNT}:rw")
}

# podman does not inherit the host environment. Forward only evaluator/runtime
# configuration names plus the exact API credentials its benchmark judges need.
mapfile -t _aar_eval_env < <(
  compgen -e | grep -E '^(AAR_|EVAL_|HARNESS_|HOLDOUT_DIR$|HELDOUT_SCORES_DIR$|SUBMISSIONS_DIR$|SCORES_DIR$|TEAM_DIR$|TARGET_MODEL(_PATH)?$|BENCHMARK_DOCS_DIR$|PYTHONPATH$|HF_(TOKEN|HOME)$|HUGGING_FACE_HUB_TOKEN$|MODEL_API_KEY$|LLAMA_API_KEY$|JUDGE_|MASK_JUDGE_MODEL$|TORCH_|PYTORCH_)' | sort -u
)
CONTAINER_ENV_PASSTHROUGH+=("${_aar_eval_env[@]}")
export DEPLOYMENT_DIR="${AAR_REPO}"

echo "[eval:vllm] container image=${AAR_VLLM_CONTAINER_IMAGE}" >&2
echo "[eval:vllm] container model_mount=${MODEL_CFG_PATH}" >&2
echo "[eval:vllm] container runtime_mount=${AAR_VLLM_CONTAINER_RW_MOUNT}" >&2
container_run - "${AAR_VLLM_CONTAINER_IMAGE}" "$@"
