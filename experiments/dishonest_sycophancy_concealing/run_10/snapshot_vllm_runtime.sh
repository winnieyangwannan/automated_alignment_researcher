#!/bin/bash
# Retain the validated evaluator launcher inside each durable attempt.
set -euo pipefail
umask 077

SOURCE="${AAR_RUN10_VLLM_RUNTIME_SOURCE:-/checkpoint/ram/shared/vllm_deployments_v2/baseline_gemma-4-31b-ib/src/serve_api_v2}"
EXPECTED_TREE_SHA256=41fd8b7fe7fafe8bda40c8f8fb240ad39061d60d69db952a90b60bdccc3f8f41
DEST="${1:?usage: $0 <attempt-dir>}/runtime/serve_api_v2"
PARENT="$(dirname -- "${DEST}")"

tree_sha256() {
  (cd -- "$1" && find . -type f ! -path '*/__pycache__/*' -print0 |
    LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')
}
verify_snapshot() {
  [ -r "$1/worker/worker_vllm.sh" ] &&
    [ -r "$1/worker/container.sh" ] &&
    [ -r "$1/worker/engine_common.sh" ] &&
    [ "$(tree_sha256 "$1")" = "${EXPECTED_TREE_SHA256}" ]
}

mkdir -p -- "${PARENT}"
if [ -e "${DEST}" ]; then
  verify_snapshot "${DEST}" || { echo "invalid existing evaluator snapshot" >&2; exit 2; }
  printf '%s\n' "${DEST}/worker/worker_vllm.sh"
  exit 0
fi
verify_snapshot "${SOURCE}" || { echo "validated evaluator source changed" >&2; exit 2; }
stage="$(mktemp -d "${PARENT}/.serve_api_v2.incomplete.XXXXXX")"
trap 'rm -rf --one-file-system -- "${stage}"' EXIT
cp -a -- "${SOURCE}/." "${stage}/"
verify_snapshot "${stage}" || { echo "copied evaluator snapshot failed validation" >&2; exit 2; }
mv -- "${stage}" "${DEST}"
trap - EXIT
printf '%s\n' "${DEST}/worker/worker_vllm.sh"
