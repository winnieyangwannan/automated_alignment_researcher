#!/bin/bash
# Atomically retain the complete, validated serve_api_v2 launcher runtime in
# durable attempt storage so deployment cleanup cannot break an in-flight run.
set -euo pipefail
umask 077

SOURCE="${AAR_RUN9_VLLM_RUNTIME_SOURCE:-/checkpoint/ram/shared/vllm_deployments_v2/.removed/aar-gemma-4-31b-it-20261007T005922Z/src/serve_api_v2}"
EXPECTED_TREE_SHA256="41fd8b7fe7fafe8bda40c8f8fb240ad39061d60d69db952a90b60bdccc3f8f41"
DEST="${1:?usage: $0 <attempt-dir>}"
DEST="${DEST}/runtime/serve_api_v2"
PARENT="$(dirname -- "${DEST}")"

tree_sha256() {
  local root="$1"
  (
    cd -- "${root}"
    find . -type f ! -path '*/__pycache__/*' -print0 |
      LC_ALL=C sort -z |
      xargs -0 sha256sum |
      sha256sum |
      awk '{print $1}'
  )
}

verify_snapshot() {
  local root="$1"
  [ -r "${root}/worker/worker_vllm.sh" ] || return 1
  [ -r "${root}/worker/container.sh" ] || return 1
  [ -r "${root}/worker/engine_common.sh" ] || return 1
  [ "$(tree_sha256 "${root}")" = "${EXPECTED_TREE_SHA256}" ]
}

mkdir -p -- "${PARENT}"
if [ -e "${DEST}" ]; then
  verify_snapshot "${DEST}" || {
    echo "existing durable vLLM runtime failed validation: ${DEST}" >&2
    exit 2
  }
  printf '%s\n' "${DEST}/worker/worker_vllm.sh"
  exit 0
fi

[ -d "${SOURCE}" ] || {
  echo "validated vLLM runtime source is missing: ${SOURCE}" >&2
  exit 2
}
verify_snapshot "${SOURCE}" || {
  echo "validated vLLM runtime source hash mismatch: ${SOURCE}" >&2
  exit 2
}

STAGING="$(mktemp -d "${PARENT}/.serve_api_v2.incomplete.XXXXXX")"
cleanup() {
  case "${STAGING}" in
    "${PARENT}"/.serve_api_v2.incomplete.*)
      rm -rf --one-file-system -- "${STAGING}"
      ;;
  esac
}
trap cleanup EXIT
cp -a -- "${SOURCE}/." "${STAGING}/"
verify_snapshot "${STAGING}" || {
  echo "copied vLLM runtime failed validation" >&2
  exit 2
}
mv -- "${STAGING}" "${DEST}"
trap - EXIT
printf '%s\n' "${DEST}/worker/worker_vllm.sh"
