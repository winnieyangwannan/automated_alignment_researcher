#!/bin/bash
#SBATCH --job-name=run12-chain-controller
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=7-00:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?missing repository}"
ATTEMPT="${AAR_RUN_ATTEMPT_DIR:?missing attempt}"
SEED="${1:?missing chain seed}"
TEAM_ID="${2:?missing team id}"
FIRST_JOB="${3:?missing first chain job}"
CHAIN_ROOT="${ATTEMPT}/chains/${SEED}"
CHECKPOINT_ROOT="${AAR_RUN12_CHECKPOINT_ROOT:?missing checkpoint artifact root}"
TEAM_DIR="${ATTEMPT}/aar_teams/${TEAM_ID}"
BASE_CHECKPOINT="${TARGET_MODEL_PATH:?missing fixed Gemma base}"
SV="${AAR_SERVE_API_V2_ROOT:?missing serve_api_v2 root}"
PY="${HARNESS_PY:?missing harness Python}"
TARGET_URL="http://fair-cw-use2-1-ingress-slurm-ingress/v1"
TARGET_HOST="ram-inference-gateway.ingress."
TARGET_MODEL="gemma-4-31B-it"
MAX_ATTEMPTS="${AAR_RUN12_MAX_CHAIN_ATTEMPTS:-8}"
TARGET_PAIRS="${AAR_RUN12_TARGET_PAIRS:-5}"
: "${AAR_AUTODATA_PROFILE_CONFIG:?missing AutoData profile YAML}"
: "${AAR_AUTODATA_RUN_CONFIG:?missing AutoData run YAML}"
: "${AAR_AUTODATA_RUNTIME_ENV:?missing compiled AutoData runtime environment}"
# shellcheck disable=SC1090
source "${AAR_AUTODATA_RUNTIME_ENV}"
[ "${AAR_AUTODATA_TARGET_REQUIRED:-0}" = 1 ] || {
  echo "Run 12 controller requires target-aware AutoData" >&2
  exit 2
}

export TEAM_DIR LOCAL_FINDINGS_DIR="${TEAM_DIR}/forum"
export SUBMISSIONS_DIR="${TEAM_DIR}/submissions" SCORES_DIR="${TEAM_DIR}/scores"
export AAR_IDEAS_DIR="${TEAM_DIR}/methods" SESSION_LOGS_DIR="${TEAM_DIR}/logs"
export LIT_FORUM_DIR="${TEAM_DIR}/litreview"
export AAR_AUTODATA_PROPOSAL_BINDINGS="${CHAIN_ROOT}/secrets/proposal-bindings.json"
export AAR_VLLM_MERGED_ROOT="${CHECKPOINT_ROOT}/chains/${SEED}/merged_candidates"
mkdir -p "${CHAIN_ROOT}/"{bindings,deployments,logs,metadata} "${AAR_VLLM_MERGED_ROOT}"

record_event() {
  printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
    | tee -a "${CHAIN_ROOT}/metadata/controller-events.tsv"
}

wait_job() {
  local job_id="$1" state=""
  while squeue -h -j "${job_id}" 2>/dev/null | grep -q .; do
    sleep 20
  done
  for _ in $(seq 1 30); do
    state="$(sacct -n -X -j "${job_id}" --format=State 2>/dev/null | awk 'NF{print $1; exit}')"
    [ -n "${state}" ] && break
    sleep 2
  done
  record_event "job=${job_id} state=${state:-unknown}"
}

pair_count() {
  "${PY}" - "${TEAM_DIR}" <<'PY'
import json
import pathlib
import sys

team = pathlib.Path(sys.argv[1])
scores = set()
for path in (team / "scores").glob("*.json"):
    if path.name.endswith(".failed.json"):
        continue
    try:
        value = json.loads(path.read_text())
    except Exception:
        continue
    if isinstance(value.get("headline_pct"), (int, float)):
        scores.add(path.stem)
results = set()
for path in (team / "forum").glob("*.json"):
    try:
        value = json.loads(path.read_text())
    except Exception:
        continue
    if value.get("finding_type") == "result" and isinstance(value.get("run_id"), str):
        results.add(value["run_id"])
print(len(scores & results))
PY
}

wait_deployment() {
  local deployment="$1" phase=""
  for _ in $(seq 1 160); do
    [ -d "/checkpoint/ram/shared/vllm_deployments_v2/${deployment}" ] || return 1
    phase="$("${SV}/serve.sh" status "${deployment}" --json 2>/dev/null | jq -r '.phase // empty' || true)"
    if [ "${phase}" = serving ]; then
      "${SV}/serve.sh" test "${deployment}" >/dev/null
      record_event "deployment=${deployment} phase=serving"
      return 0
    fi
    case "${phase}" in failed|stopped|expired) return 1;; esac
    sleep 15
  done
  return 1
}

deploy_checkpoint() {
  local deployment="$1" checkpoint="$2"
  env -u SSL_CERT_FILE -u NODE_EXTRA_CA_CERTS \
    -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    -u NO_PROXY -u no_proxy \
    "${SV}/serve.sh" deploy "${deployment}" \
      --model gemma-4-31B-it --checkpoint "${checkpoint}" --endpoints 1 \
      --image docker.io/vllm/vllm-openai:v0.25.1 \
      --cluster fair-cw-use2-1 --partition g3 --account ram --qos g3_ram_high \
      --coord-qos cpu_x86_lowest --proxy-qos cpu_x86_lowest \
      --gateway-register --lifetime 7d --no-watch
  wait_deployment "${deployment}"
}

submit_session() {
  # Rebuild the same positive allowlist used by launch_team.sh.  The changed
  # policy path is inherited; provider/operator secrets remain excluded.
  # shellcheck disable=SC1091
  source "${REPO}/scripts/aar_runtime_env.sh"
  local names=() name csv job
  export AAR_IDEA_UID_OVERRIDE="run12-${SEED}-iteration-${next_iteration}"
  export AAR_RESUME_APPROVED_PROPOSAL=1
  for name in "${AAR_RESEARCH_CHAIN_ENV_ALLOWLIST[@]}"; do
    [[ -v "${name}" ]] && names+=("${name}")
  done
  csv="$(IFS=,; printf '%s' "${names[*]}")"
  job="$(sbatch --parsable --account=ram --partition=g3 --qos=g3_ram_high \
    --time="${AAR_CHAIN_MAX_HOURS:-72}:30:00" \
    --job-name="aar-run12-${SEED}" \
    --output="${TEAM_DIR}/logs/%x_%j.out" --export="${csv}" \
    "${REPO}/scripts/slurm_aar_chain.sh" "explore-${SEED}" \
    "${AAR_CHAIN_MAX_HOURS:-72}" 1 "${TEAM_ID}")"
  printf '%s\n' "${job}"
}

current="${CHAIN_ROOT}/metadata/incumbent.json"
current_target="${CHAIN_ROOT}/bindings/iteration-1.json"
current_policy="${CHAIN_ROOT}/metadata/campaign-policy.json"
current_contract="${CHAIN_ROOT}/metadata/autodata-training-data-contract.json"
current_deployment="$(jq -r '.endpoint.deployment_id' "${current_target}")"
attempts=1
export AAR_AUTODATA_TRAINING_DATA_CONTRACT="${current_contract}"

wait_job "${FIRST_JOB}"
if [ "${AAR_AUTODATA_STOP_AFTER:-}" = production ]; then
  next_iteration=1
  while true; do
    shopt -s nullglob
    markers=("${TEAM_DIR}"/autodata/*/production-canary-complete.json)
    shopt -u nullglob
    if [ "${#markers[@]}" -eq 1 ] && jq -e \
      --argjson required "${AAR_AUTODATA_PRODUCTION_ROWS:?}" '
        .schema == "aar.autodata.production-canary-complete/v1"
        and .stop_after == "production"
        and .required_accepted_rows == $required
        and .verification.available_rows >= $required
        and .verification.run_id == .run_id
      ' "${markers[0]}" >/dev/null; then
      cp -- "${markers[0]}" "${CHAIN_ROOT}/metadata/production-canary-complete.json"
      record_event "complete=production_canary accepted_rows=$(jq -r '.verification.available_rows' "${markers[0]}") attempts=${attempts}"
      jq -n \
        --arg chain "${SEED}" \
        --arg marker "${markers[0]}" \
        --argjson attempts "${attempts}" \
        --argjson required "${AAR_AUTODATA_PRODUCTION_ROWS}" \
        '{schema:"aar.run12.production-canary/v1",chain:$chain,stop_after:"production",required_accepted_rows:$required,attempts:$attempts,marker:$marker}' \
        > "${CHAIN_ROOT}/metadata/complete.json"
      exit 0
    fi
    if [ "${#markers[@]}" -gt 1 ]; then
      record_event "fatal=multiple_production_canary_markers count=${#markers[@]}"
      exit 1
    fi
    if [ "${attempts}" -ge "${MAX_ATTEMPTS}" ]; then
      record_event "fatal=production_canary_not_completed attempts=${attempts}"
      exit 1
    fi
    job="$(submit_session)"
    attempts=$((attempts + 1))
    record_event "production_canary_retry=${job} attempts=${attempts}"
    wait_job "${job}"
  done
fi
pairs="$(pair_count)"
while [ "${pairs}" -lt "${TARGET_PAIRS}" ]; do
  if [ "${attempts}" -ge "${MAX_ATTEMPTS}" ]; then
    record_event "fatal=attempt_budget_exhausted pairs=${pairs} attempts=${attempts}"
    exit 1
  fi

  next_iteration=$((pairs + 1))
  selected="${CHAIN_ROOT}/metadata/incumbent.next.json"
  if ! PYTHONPATH="${REPO}" "${PY}" -m aar.aar_chain_promotion \
      --team-dir "${TEAM_DIR}" --merged-root "${AAR_VLLM_MERGED_ROOT}" \
      --current "${current}" \
      --expected-suite honesty_sycophancy_concealing_uncertainty \
      --output "${selected}"; then
    # No valid candidate yet: the correct parent remains the verified base.
    cp -- "${current}" "${selected}"
  fi

  changed="$(jq -r '.changed' "${selected}")"
  if [ "${changed}" = true ]; then
    run_id="$(jq -r '.run_id' "${selected}")"
    merged="$(jq -r '.merged_checkpoint' "${selected}")"
    adapter="$(jq -r '.adapter_checkpoint' "${selected}")"
    short_hash="$(sha256sum "${adapter}/adapter_model.safetensors" | cut -c1-10)"
    new_deployment="winnieyangwn-r12-${SEED}-i${next_iteration}-${short_hash}"
    record_event "promotion=${run_id} iteration=${next_iteration} deployment=${new_deployment}"
    deploy_checkpoint "${new_deployment}" "${merged}"
    binding="${CHAIN_ROOT}/bindings/iteration-${next_iteration}.json"
    PYTHONPATH="${REPO}" "${PY}" -m aar.autodata_target_binding create \
      --iteration "${next_iteration}" --chain-id "${SEED}" \
      --incumbent-run-id "${run_id}" \
      --base-checkpoint "${BASE_CHECKPOINT}" --adapter-checkpoint "${adapter}" \
      --merged-checkpoint "${merged}" --target-url "${TARGET_URL}" \
      --target-host-header "${TARGET_HOST}" --target-model "${TARGET_MODEL}" \
      --target-deployment-id "${new_deployment}" --output "${binding}"
    jq --arg deployment "${new_deployment}" \
      '. + {deployment_id:$deployment, changed:false}' "${selected}" \
      > "${current}.tmp"
    chmod 600 "${current}.tmp"
    mv -- "${current}.tmp" "${current}"
    old_deployment="${current_deployment}"
    current_deployment="${new_deployment}"
    current_target="${binding}"
    if [ "${old_deployment}" != "${new_deployment}" ]; then
      "${SV}/serve.sh" stop "${old_deployment}" >/dev/null || true
      record_event "retired_deployment=${old_deployment}"
    fi
  elif [ "$(jq -r '.run_id // empty' "${current}")" != "" ]; then
    run_id="$(jq -r '.run_id' "${current}")"
    binding="${CHAIN_ROOT}/bindings/iteration-${next_iteration}.json"
    PYTHONPATH="${REPO}" "${PY}" -m aar.autodata_target_binding create \
      --iteration "${next_iteration}" --chain-id "${SEED}" \
      --incumbent-run-id "${run_id}" \
      --base-checkpoint "${BASE_CHECKPOINT}" \
      --adapter-checkpoint "$(jq -r '.adapter_checkpoint' "${current}")" \
      --merged-checkpoint "$(jq -r '.merged_checkpoint' "${current}")" \
      --target-url "${TARGET_URL}" --target-host-header "${TARGET_HOST}" \
      --target-model "${TARGET_MODEL}" --target-deployment-id "${current_deployment}" \
      --output "${binding}"
    current_target="${binding}"
  else
    binding="${CHAIN_ROOT}/bindings/iteration-${next_iteration}.json"
    PYTHONPATH="${REPO}" "${PY}" -m aar.autodata_campaign_policy create-base-target \
      --iteration "${next_iteration}" --chain-id "${SEED}" \
      --base-checkpoint "${BASE_CHECKPOINT}" \
      --target-url "${TARGET_URL}" --target-host-header "${TARGET_HOST}" \
      --target-model "${TARGET_MODEL}" --target-deployment-id "${current_deployment}" \
      --output "${binding}"
    current_target="${binding}"
  fi

  PYTHONPATH="${REPO}" "${PY}" -m aar.autodata_run_config compile \
    --profile "${AAR_AUTODATA_PROFILE_CONFIG}" --run "${AAR_AUTODATA_RUN_CONFIG}" \
    --target-binding "${current_target}" --chain "${SEED}" --repo "${REPO}" \
    --output-dir "${CHAIN_ROOT}/metadata" >/dev/null
  # shellcheck disable=SC1090
  source "${AAR_AUTODATA_RUNTIME_ENV}"
  [ "${AAR_AUTODATA_TARGET_REQUIRED:-0}" = 1 ] || {
    record_event "fatal=compiled_configuration_not_target_aware"
    exit 2
  }

  before="${pairs}"
  job="$(submit_session)"
  attempts=$((attempts + 1))
  record_event "iteration=${next_iteration} session_job=${job} before_pairs=${before}"
  wait_job "${job}"
  pairs="$(pair_count)"
  if [ "${pairs}" -le "${before}" ]; then
    record_event "session_job=${job} produced_no_pair retrying_same_iteration=${next_iteration}"
  else
    record_event "completed_pairs=${pairs} attempts=${attempts}"
  fi
done

record_event "complete pairs=${pairs} attempts=${attempts} final_deployment=${current_deployment}"
printf '{"chain":"%s","pairs":%s,"attempts":%s,"final_deployment":"%s"}\n' \
  "${SEED}" "${pairs}" "${attempts}" "${current_deployment}" \
  > "${CHAIN_ROOT}/metadata/complete.json"
