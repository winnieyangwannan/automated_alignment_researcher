#!/bin/bash
#SBATCH --job-name=run13-canary-controller
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=7-00:00:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?missing repository}"
[ "${AAR_EXPERIMENT_RUN_ID:?missing experiment identity}" = run13 ] || {
  echo "Run 13 controller rejects another experiment identity" >&2; exit 2;
}
EXPERIMENT_RUN_ID=run13
TRIAL_ID="${AAR_RUN13_TRIAL_ID:?missing Run 13 trial identity}"
[[ "${TRIAL_ID}" =~ ^trial[1-9][0-9]*$ ]] || {
  echo "invalid Run 13 trial identity" >&2; exit 2;
}
# Reapply the trusted runtime selection before the controller captures PY; the
# controller is long-lived and resubmits research jobs after the launcher exits.
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"
ATTEMPT="${AAR_RUN_ATTEMPT_DIR:?missing attempt}"
SEED="${1:?missing chain seed}"
TEAM_ID="${2:?missing team id}"
FIRST_JOB="${3:?missing first chain job}"
CHAIN_ROOT="${ATTEMPT}/chains/${SEED}"
CHECKPOINT_ROOT="${AAR_AUTODATA_CHECKPOINT_ROOT:-${AAR_RUN13_CHECKPOINT_ROOT:?missing checkpoint artifact root}}"
TEAM_DIR="${ATTEMPT}/aar_teams/${TEAM_ID}"
BASE_CHECKPOINT="${TARGET_MODEL_PATH:?missing fixed Gemma base}"
SV="${AAR_SERVE_API_V2_ROOT:?missing serve_api_v2 root}"
PY="${HARNESS_PY:?missing harness Python}"
TARGET_URL="http://fair-cw-use2-1-ingress-slurm-ingress/v1"
TARGET_HOST="ram-inference-gateway.ingress."
TARGET_MODEL="gemma-4-31B-it"
MAX_ATTEMPTS="${AAR_RUN13_MAX_CHAIN_ATTEMPTS:?missing chain-attempt ceiling}"
TARGET_PAIRS="${AAR_RUN13_TARGET_PAIRS:?missing target-pair count}"
if [ "${SEED}" != alpha ] || [ "${MAX_ATTEMPTS}" != 2 ] || [ "${TARGET_PAIRS}" != 1 ]; then
  echo "Run 13 controller is restricted to alpha, two session attempts, and one structural pair" >&2
  exit 2
fi
[ "${AAR_AUTODATA_STOP_AFTER:?missing stop boundary}" = training_smoke ] || {
  echo "Run 13 controller must stop after training_smoke" >&2; exit 2;
}
: "${AAR_AUTODATA_PROFILE_CONFIG:?missing AutoData profile YAML}"
: "${AAR_AUTODATA_RUN_CONFIG:?missing AutoData run YAML}"
: "${AAR_AUTODATA_RUNTIME_ENV:?missing compiled AutoData runtime environment}"
# shellcheck disable=SC1090
source "${AAR_AUTODATA_RUNTIME_ENV}"
[ "${AAR_AUTODATA_TARGET_REQUIRED:-0}" = 1 ] || {
  echo "${EXPERIMENT_RUN_ID} controller requires target-aware AutoData" >&2
  exit 2
}

export TEAM_DIR LOCAL_FINDINGS_DIR="${TEAM_DIR}/forum"
export SUBMISSIONS_DIR="${TEAM_DIR}/submissions" SCORES_DIR="${TEAM_DIR}/scores"
export AAR_IDEAS_DIR="${TEAM_DIR}/methods" SESSION_LOGS_DIR="${TEAM_DIR}/logs"
export LIT_FORUM_DIR="${TEAM_DIR}/litreview"
export AAR_AUTODATA_PROPOSAL_BINDINGS="${CHAIN_ROOT}/secrets/proposal-bindings.json"
export AAR_VLLM_MERGED_ROOT="${CHECKPOINT_ROOT}/chains/${SEED}/merged_candidates"
mkdir -p "${CHAIN_ROOT}/"{bindings,deployments,logs,metadata} "${AAR_VLLM_MERGED_ROOT}"
SUBMISSION_INTENTS="${CHAIN_ROOT}/metadata/submission-intents"
mkdir -p "${SUBMISSION_INTENTS}"
chmod 700 "${SUBMISSION_INTENTS}"
exec 8>"${CHAIN_ROOT}/metadata/controller.lock"
flock -n 8 || {
  echo "another ${EXPERIMENT_RUN_ID} controller owns chain ${SEED}" >&2
  exit 2
}

record_event() {
  printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
    | tee -a "${CHAIN_ROOT}/metadata/controller-events.tsv"
}

wait_job() {
  local job_id="$1" state="" slurm_exit="" accounting=""
  local classification="" terminal="false"
  local unknown_since="" now="" timeout="${AAR_RUN13_SACCT_UNKNOWN_TIMEOUT_SECONDS:-900}"
  while true; do
    # squeue is advisory only. A transient squeue outage or disappearance never
    # constitutes completion; sacct is the authoritative terminal record.
    squeue -h -j "${job_id}" -o '%T' >/dev/null 2>&1 || true
    accounting="$(sacct -n -X -j "${job_id}" --format=State,ExitCode -P \
      2>/dev/null | awk 'NF{print; exit}')"
    state="${accounting%%|*}"
    slurm_exit="${accounting#*|}"
    [ "${slurm_exit}" != "${accounting}" ] || slurm_exit=""
    classification="$(PYTHONPATH="${REPO}" "${PY}" -m \
      aar.slurm_session_recovery classify --state "${state}")"
    terminal="$(jq -r '.terminal' <<<"${classification}")"
    if [ "${terminal}" = true ]; then
      break
    fi
    now="$(date +%s)"
    if [ -z "${state}" ]; then
      [ -n "${unknown_since}" ] || unknown_since="${now}"
      if [ $((now - unknown_since)) -ge "${timeout}" ]; then
        record_event "fatal=sacct_state_unavailable job=${job_id} waited_seconds=${timeout}"
        return 75
      fi
    else
      unknown_since=""
    fi
    sleep 20
  done
  LAST_JOB_ID="${job_id}"
  LAST_JOB_STATE="$(jq -r '.state' <<<"${classification}")"
  LAST_JOB_RETRYABLE="$(jq -r '.retryable' <<<"${classification}")"
  LAST_JOB_CATEGORY="$(jq -r '.category' <<<"${classification}")"
  PYTHONPATH="${REPO}" "${PY}" -m aar.slurm_session_recovery \
    reconcile-result \
    --path "${TEAM_DIR}/logs/research-session-result-${job_id}.json" \
    --job-id "${job_id}" --state "${LAST_JOB_STATE}" \
    --exit-code "${slurm_exit:-unknown}" >/dev/null
  record_event "job=${job_id} state=${LAST_JOB_STATE} category=${LAST_JOB_CATEGORY} retryable=${LAST_JOB_RETRYABLE}"
}

require_retryable_terminal() {
  local context="$1"
  if [ "${LAST_JOB_RETRYABLE:-false}" != true ]; then
    record_event "fatal=${context} job=${LAST_JOB_ID:-unknown} state=${LAST_JOB_STATE:-unknown} category=${LAST_JOB_CATEGORY:-unknown} retryable=false"
    return 1
  fi
}

reconcile_submission_comment() {
  local comment="$1" queue_output="" accounting_output="" matches=""
  queue_output="$(squeue -h --me -o '%A|%k' 2>/dev/null || true)"
  accounting_output="$(sacct -n -X --starttime "$(date -d '8 days ago' +%F)" \
    --format=JobIDRaw,Comment -P 2>/dev/null || true)"
  matches="$({ printf '%s\n' "${queue_output}"; printf '%s\n' "${accounting_output}"; } \
    | awk -F'|' -v wanted="${comment}" '$2 == wanted && $1 ~ /^[0-9]+$/ {print $1}' \
    | sort -nu)"
  if [ "$(wc -l <<<"${matches}")" -gt 1 ]; then
    record_event "fatal=ambiguous_submission_intent comment=${comment} jobs=$(tr '\n' ',' <<<"${matches}")"
    return 2
  fi
  printf '%s' "${matches}"
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
  local attempt_number="$1" names=() name csv job intent key comment status match
  export AAR_IDEA_UID_OVERRIDE="run13-${TRIAL_ID}-${SEED}-iteration-${next_iteration}"
  export AAR_RESUME_APPROVED_PROPOSAL=1
  for name in "${AAR_RESEARCH_CHAIN_ENV_ALLOWLIST[@]}"; do
    [[ -v "${name}" ]] && names+=("${name}")
  done
  csv="$(IFS=,; printf '%s' "${names[*]}")"
  intent="${SUBMISSION_INTENTS}/attempt-${attempt_number}.json"
  key="${TEAM_ID}:${SEED}:${attempt_number}:${next_iteration}"
  comment="aar-${EXPERIMENT_RUN_ID}:${TEAM_ID}:${SEED}:${attempt_number}"
  PYTHONPATH="${REPO}" "${PY}" -m aar.slurm_session_recovery \
    prepare --path "${intent}" --key "${key}" --comment "${comment}" >/dev/null
  status="$(PYTHONPATH="${REPO}" "${PY}" -m aar.slurm_session_recovery \
    show --path "${intent}")"
  if [ "$(jq -r '.status' <<<"${status}")" = registered ]; then
    jq -r '.job_id' <<<"${status}"
    return 0
  fi
  if [ "$(jq -r '.status' <<<"${status}")" = submitting ]; then
    # A prior controller may have crashed after sbatch accepted the job but
    # before registration. Reconcile the unique durable comment; never guess
    # that an empty scheduler response permits a duplicate submission.
    for _ in $(seq 1 30); do
      match="$(reconcile_submission_comment "${comment}")"
      [ -n "${match}" ] && break
      sleep 2
    done
    if [ -z "${match}" ]; then
      record_event "fatal=submission_reconciliation_timeout intent=${intent} comment=${comment}"
      return 75
    fi
    PYTHONPATH="${REPO}" "${PY}" -m aar.slurm_session_recovery \
      transition --path "${intent}" --status registered --job-id "${match}" >/dev/null
    printf '%s\n' "${match}"
    return 0
  fi
  PYTHONPATH="${REPO}" "${PY}" -m aar.slurm_session_recovery \
    transition --path "${intent}" --status submitting >/dev/null
  if ! job="$(sbatch --parsable --account=ram --partition=g3 --qos=g3_ram_high \
    --time="${AAR_CHAIN_MAX_HOURS:-72}:30:00" \
    --job-name="aar-${EXPERIMENT_RUN_ID}-${SEED}" \
    --comment="${comment}" \
    --output="${TEAM_DIR}/logs/%x_%j.out" --export="${csv}" \
    "${REPO}/scripts/slurm_aar_chain.sh" "explore-${SEED}" \
    "${AAR_CHAIN_MAX_HOURS:-72}" 1 "${TEAM_ID}")"; then
    # The client may have lost the response after Slurm accepted the job.
    # Retain "submitting" so a restarted controller reconciles by comment.
    record_event "fatal=sbatch_submission_ambiguous intent=${intent} comment=${comment}"
    return 75
  fi
  job="${job%%;*}"
  [[ "${job}" =~ ^[0-9]+$ ]] || {
    record_event "fatal=invalid_sbatch_job_id intent=${intent}"
    return 1
  }
  PYTHONPATH="${REPO}" "${PY}" -m aar.slurm_session_recovery \
    transition --path "${intent}" --status registered --job-id "${job}" >/dev/null
  printf '%s\n' "${job}"
}

current="${CHAIN_ROOT}/metadata/incumbent.json"
current_target="${CHAIN_ROOT}/bindings/iteration-1.json"
current_contract="${CHAIN_ROOT}/metadata/autodata-training-data-contract.json"
current_deployment="$(jq -r '.endpoint.deployment_id' "${current_target}")"
registered_retries="$(PYTHONPATH="${REPO}" "${PY}" -m \
  aar.slurm_session_recovery count-registered \
  --directory "${SUBMISSION_INTENTS}")"
attempts=$((1 + registered_retries))
active_job="${FIRST_JOB}"
if [ "${registered_retries}" -gt 0 ]; then
  latest_intent="$(find "${SUBMISSION_INTENTS}" -maxdepth 1 -type f \
    -name 'attempt-*.json' -print | sort -V \
    | while read -r candidate; do
        if [ "$(jq -r '.status' "${candidate}")" = registered ]; then
          printf '%s\n' "${candidate}"
        fi
      done | tail -n 1)"
  active_job="$(jq -r '.job_id' "${latest_intent}")"
  record_event "controller_restart_reconciled=${active_job} intent=${latest_intent} attempts=${attempts}"
fi
export AAR_AUTODATA_TRAINING_DATA_CONTRACT="${current_contract}"

wait_job "${active_job}"
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
        --arg schema "aar.${EXPERIMENT_RUN_ID}.production-canary/v1" \
        --arg chain "${SEED}" \
        --arg marker "${markers[0]}" \
        --argjson attempts "${attempts}" \
        --argjson required "${AAR_AUTODATA_PRODUCTION_ROWS}" \
        '{schema:$schema,chain:$chain,stop_after:"production",required_accepted_rows:$required,attempts:$attempts,marker:$marker}' \
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
    require_retryable_terminal "production_canary_session_failed"
    job="$(submit_session "$((attempts + 1))")"
    attempts=$((attempts + 1))
    record_event "production_canary_retry=${job} attempts=${attempts}"
    wait_job "${job}"
  done
fi
if [ "${AAR_AUTODATA_STOP_AFTER:-}" = training_smoke ]; then
  next_iteration=1
  while true; do
    shopt -s nullglob
    markers=("${TEAM_DIR}"/autodata/*/training-smoke-canary-complete.json)
    shopt -u nullglob
    if [ "${#markers[@]}" -eq 1 ] && jq -e \
      --argjson required "${AAR_AUTODATA_PRODUCTION_ROWS:?}" '
        .schema == "aar.autodata.training-smoke-canary-complete/v1"
        and .stop_after == "training_smoke"
        and .required_accepted_rows == $required
        and .verification.available_rows >= $required
        and .training.consumed_rows == $required
        and .training.optimizer_steps == 1
        and .verification.run_id == .run_id
      ' "${markers[0]}" >/dev/null; then
      cp -- "${markers[0]}" "${CHAIN_ROOT}/metadata/training-smoke-canary-complete.json"
      record_event "complete=training_smoke_canary accepted_rows=$(jq -r '.verification.available_rows' "${markers[0]}") consumed_rows=$(jq -r '.training.consumed_rows' "${markers[0]}") attempts=${attempts}"
      jq -n \
        --arg schema "aar.${EXPERIMENT_RUN_ID}.training-smoke-canary/v1" \
        --arg chain "${SEED}" \
        --arg marker "${markers[0]}" \
        --argjson attempts "${attempts}" \
        --argjson required "${AAR_AUTODATA_PRODUCTION_ROWS}" \
        '{schema:$schema,chain:$chain,stop_after:"training_smoke",required_accepted_rows:$required,optimizer_steps:1,attempts:$attempts,marker:$marker}' \
        > "${CHAIN_ROOT}/metadata/complete.json"
      exit 0
    fi
    if [ "${#markers[@]}" -gt 1 ]; then
      record_event "fatal=multiple_training_smoke_canary_markers count=${#markers[@]}"
      exit 1
    fi
    if [ "${attempts}" -ge "${MAX_ATTEMPTS}" ]; then
      record_event "fatal=training_smoke_canary_not_completed attempts=${attempts}"
      exit 1
    fi
    require_retryable_terminal "training_smoke_session_failed"
    job="$(submit_session "$((attempts + 1))")"
    attempts=$((attempts + 1))
    record_event "training_smoke_canary_retry=${job} attempts=${attempts}"
    wait_job "${job}"
  done
fi
pairs="$(pair_count)"
if [ "${pairs}" -eq 0 ]; then
  require_retryable_terminal "initial_session_produced_no_pair"
elif [ -n "${latest_intent:-}" ]; then
  latest_iteration="$(jq -r '.key | split(":") | last | tonumber' "${latest_intent}")"
  if [ "${latest_iteration}" -gt "${pairs}" ]; then
    require_retryable_terminal "reconciled_session_produced_no_pair"
  fi
fi
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
    new_deployment="winnieyangwn-${EXPERIMENT_RUN_ID}-${SEED}-i${next_iteration}-${short_hash}"
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
  job="$(submit_session "$((attempts + 1))")"
  attempts=$((attempts + 1))
  record_event "iteration=${next_iteration} session_job=${job} before_pairs=${before}"
  wait_job "${job}"
  pairs="$(pair_count)"
  if [ "${pairs}" -le "${before}" ]; then
    require_retryable_terminal "session_produced_no_pair"
    record_event "session_job=${job} produced_no_pair infrastructure_retry_same_iteration=${next_iteration}"
  else
    record_event "completed_pairs=${pairs} attempts=${attempts}"
  fi
done

record_event "complete pairs=${pairs} attempts=${attempts} final_deployment=${current_deployment}"
printf '{"chain":"%s","pairs":%s,"attempts":%s,"final_deployment":"%s"}\n' \
  "${SEED}" "${pairs}" "${attempts}" "${current_deployment}" \
  > "${CHAIN_ROOT}/metadata/complete.json"
