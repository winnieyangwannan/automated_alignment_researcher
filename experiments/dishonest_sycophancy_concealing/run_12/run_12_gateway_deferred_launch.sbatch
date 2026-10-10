#!/bin/bash
# Wait for the shared inference gateway, then invoke the canonical Run 12 launcher.
#SBATCH --job-name=aar-run12-gateway-gate
#SBATCH --account=everyone
#SBATCH --partition=cpu_x86
#SBATCH --qos=cpu_x86_lowest
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=04:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?missing immutable Run 12 source checkout}"
EXPECTED_COMMIT="${AAR_RUN12_EXPECTED_COMMIT:?missing pinned Run 12 commit}"
STORAGE_ROOT="${AAR_RUN12_STORAGE_ROOT:-/checkpoint/ram/${USER:?}}"
INGRESS="http://fair-cw-use2-1-ingress-slurm-ingress"
HOST_HEADER="ram-inference-gateway.ingress."
GENERATOR_DEPLOYMENT="aar_8-kimi26"
GENERATOR_MODEL="Kimi-K2.6"
WAIT_SECONDS="${AAR_RUN12_GATEWAY_WAIT_SECONDS:-10800}"
POLL_SECONDS="${AAR_RUN12_GATEWAY_POLL_SECONDS:-30}"

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 12 requires branch autodata" >&2
  exit 2
}
[ "$(git -C "${REPO}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || {
  echo "Run 12 source commit drift" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "Run 12 source has tracked changes" >&2
  exit 2
fi

mkdir -p "${STORAGE_ROOT}/aar-runs"
STORAGE_ROOT="$(realpath -e -- "${STORAGE_ROOT}")"
[ "${STORAGE_ROOT}" = "/checkpoint/ram/${USER}" ] || {
  echo "Run 12 storage root must be /checkpoint/ram/${USER}" >&2
  exit 2
}

response="$(mktemp "${SLURM_TMPDIR:-/tmp}/run12-gateway-response.XXXXXX")"
models="$(mktemp "${SLURM_TMPDIR:-/tmp}/run12-gateway-models.XXXXXX")"
status="$(mktemp "${SLURM_TMPDIR:-/tmp}/run12-gateway-status.XXXXXX")"
trap 'rm -f -- "${response}" "${models}" "${status}"' EXIT

deadline=$((SECONDS + WAIT_SECONDS))
polls=0
while (( SECONDS < deadline )); do
  polls=$((polls + 1))
  health_code="$(curl -sS --noproxy '*' --max-time 15 -o /dev/null -w '%{http_code}' \
    -H "Host: ${HOST_HEADER}" "${INGRESS}/health" || true)"
  if [ "${health_code}" = 200 ] && \
      curl -fsS --noproxy '*' --max-time 15 -H "Host: ${HOST_HEADER}" \
        "${INGRESS}/status" -o "${status}" && \
      jq -e '.role == "leader" or .role == "unfenced"' "${status}" >/dev/null && \
      curl -fsS --noproxy '*' --max-time 30 -H "Host: ${HOST_HEADER}" \
        "${INGRESS}/v1/models" -o "${models}" && \
      jq -e --arg model "${GENERATOR_MODEL}" --arg deployment "${GENERATOR_DEPLOYMENT}" \
        'any(.data[]; .id == $model and .deployment == $deployment)' \
        "${models}" >/dev/null; then
    probe_code="$(curl -sS --noproxy '*' --max-time 90 -o "${response}" -w '%{http_code}' \
      -H "Host: ${HOST_HEADER}" -H "Content-Type: application/json" \
      -H "X-Deployment-Id: ${GENERATOR_DEPLOYMENT}" \
      --data '{"model":"Kimi-K2.6","messages":[{"role":"user","content":"Reply with OK."}],"temperature":0,"max_tokens":8}' \
      "${INGRESS}/v1/chat/completions" || true)"
    if [ "${probe_code}" = 200 ] && jq -e '.choices[0].message.content | type == "string"' \
        "${response}" >/dev/null; then
      echo "[run12-gateway-gate] healthy leader, registered Kimi route, and completion verified"
      export AAR_RUN12_STORAGE_ROOT="${STORAGE_ROOT}"
      exec bash "${REPO}/experiments/dishonest_sycophancy_concealing/run_12/submit_run_12_full.sh"
    fi
  fi
  if (( polls % 10 == 0 )); then
    echo "[run12-gateway-gate] waiting for healthy Kimi gateway route polls=${polls} health=${health_code:-none}"
  fi
  sleep "${POLL_SECONDS}"
done

echo "Run 12 gateway gate timed out after ${WAIT_SECONDS}s" >&2
exit 1
