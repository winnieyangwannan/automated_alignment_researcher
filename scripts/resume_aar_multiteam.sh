#!/bin/bash
# Resume selected chains from an existing multi-team AAR attempt.
#
# The experiment wrapper must load the original runtime configuration first and
# provide the policy variables documented below.  This engine deliberately
# preserves every completed score/finding and archives interrupted claim and
# training state before launching replacements.

set -euo pipefail
umask 077

ATTEMPT_DIR="$(realpath -e -- "${1:?usage: $0 <attempt-dir> [\"seed ...\"]}")"
REQUESTED_SEEDS="${2:-${AAR_RESUME_DEFAULT_SEEDS:-}}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${AAR_REPO:-}" ] && [ -d "${AAR_REPO}/aar" ]; then
  REPO="$(cd -- "${AAR_REPO}" && pwd)"
else
  REPO="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
fi
export AAR_REPO="${REPO}"
# Rebuild the positive research-chain allowlist in this process. Bash arrays do
# not survive the exec boundary from an experiment wrapper.
# shellcheck disable=SC1091
source "${REPO}/scripts/aar_runtime_env.sh"

: "${SUITE_NAME:?source the experiment runtime configuration before resuming}"
: "${AAR_RESUME_EXPECTED_BRANCH:?set the required source branch}"
: "${AAR_RESUME_EXPECTED_MODE:?set the required attempt mode}"
: "${AAR_RESUME_ALLOWED_SEEDS:?set the allowed seed list}"
: "${AAR_RESUME_TEAM_PREFIX:?set the team directory prefix}"
: "${AAR_RESUME_TEAM_SUFFIX:?set the team directory suffix}"
: "${AAR_RESUME_MAX_SESSIONS:?set the original per-chain session ceiling}"
: "${AAR_RESUME_HOURS:?set replacement-chain wall-clock hours}"
: "${AAR_RESUME_JOB_PREFIX:?set the recovery job prefix}"
: "${AAR_EVAL_IDLE_SECONDS:?missing evaluator idle timeout}"
: "${HARNESS_PY:?set the trusted harness Python}"

case "${AAR_NO_LOCAL_GPU:-}" in
  1|true|TRUE|yes|YES|on|ON) ;;
  *) echo "recovery requires AAR_NO_LOCAL_GPU=true for decoupled training" >&2; exit 2;;
esac

case "${AAR_RESUME_MAX_SESSIONS}" in
  ''|0|*[!0-9]*) echo "invalid session ceiling" >&2; exit 2;;
esac
case "${AAR_RESUME_HOURS}" in
  ''|0|*[!0-9]*) echo "invalid recovery hours" >&2; exit 2;;
esac
[[ "${AAR_RESUME_JOB_PREFIX}" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "unsafe recovery job prefix" >&2
  exit 2
}

read -r -a requested_seeds <<< "${REQUESTED_SEEDS}"
read -r -a allowed_seeds <<< "${AAR_RESUME_ALLOWED_SEEDS}"
[ "${#requested_seeds[@]}" -gt 0 ] || { echo "no recovery seeds requested" >&2; exit 2; }

current_branch="$(git -C "${REPO}" branch --show-current)"
[ "${current_branch}" = "${AAR_RESUME_EXPECTED_BRANCH}" ] || {
  echo "recovery requires branch ${AAR_RESUME_EXPECTED_BRANCH}; found ${current_branch}" >&2
  exit 2
}
if ! git -C "${REPO}" diff --quiet || ! git -C "${REPO}" diff --cached --quiet; then
  echo "tracked worktree is dirty" >&2
  exit 2
fi

submission="${ATTEMPT_DIR}/metadata/submission.txt"
children="${ATTEMPT_DIR}/metadata/children.tsv"
if [ ! -f "${submission}" ] || [ ! -f "${children}" ]; then
  echo "attempt is missing submission.txt or children.tsv" >&2
  exit 2
fi
recorded_attempt="$(sed -n 's/^attempt_dir=//p' "${submission}")"
[ "${recorded_attempt}" = "${ATTEMPT_DIR}" ] || {
  echo "submission metadata is bound to another attempt: ${recorded_attempt:-missing}" >&2
  exit 2
}
recorded_mode="$(sed -n 's/^mode=//p' "${submission}")"
[ "${recorded_mode}" = "${AAR_RESUME_EXPECTED_MODE}" ] || {
  echo "target mode is ${recorded_mode:-missing}, expected ${AAR_RESUME_EXPECTED_MODE}" >&2
  exit 2
}
original_commit="$(sed -n 's/^git_commit=//p' "${submission}")"
[[ "${original_commit}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "submission metadata has no full source commit" >&2
  exit 2
}
git -C "${REPO}" merge-base --is-ancestor "${original_commit}" HEAD || {
  echo "recovery source does not descend from original commit ${original_commit}" >&2
  exit 2
}

valid_seed() {
  local candidate="$1" allowed
  [[ "${candidate}" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
  for allowed in "${allowed_seeds[@]}"; do
    [ "${candidate}" = "${allowed}" ] && return 0
  done
  return 1
}

seed_requested() {
  local candidate="$1" requested
  for requested in "${requested_seeds[@]}"; do
    [ "${candidate}" = "${requested}" ] && return 0
  done
  return 1
}

for seed in "${requested_seeds[@]}"; do
  valid_seed "${seed}" || {
    echo "invalid or disallowed recovery seed: ${seed}" >&2
    exit 2
  }
done

job_active() {
  local job="$1"
  [[ "${job}" =~ ^[0-9]+$ ]] || return 1
  [ -n "$(squeue -h -j "${job}" -o '%T' 2>/dev/null | head -1)" ]
}

job_state() {
  local job="$1"
  sacct -j "${job}" -X -n -P -o State 2>/dev/null \
    | awk -F'|' 'NF && $1 != "" {sub(/[ +].*$/, "", $1); print toupper($1); exit}'
}

registry="${ATTEMPT_DIR}/metadata/recovery_jobs.tsv"
lock="${ATTEMPT_DIR}/metadata/recovery_jobs.lock"
exec 9>"${lock}"
flock -n 9 || { echo "another recovery is already running for this attempt" >&2; exit 2; }

# Fail closed before moving any stale state.  Original evaluator/chain jobs,
# earlier recovery jobs, and retained training receipts all participate.
active_jobs=()
while IFS=$'\t' read -r seed evaluator chain extra; do
  [ -z "${extra:-}" ] || { echo "invalid children.tsv row for ${seed}" >&2; exit 2; }
  valid_seed "${seed}" || { echo "invalid child seed: ${seed}" >&2; exit 2; }
  seed_requested "${seed}" || continue
  for job in "${evaluator}" "${chain}"; do
    [[ "${job}" =~ ^[0-9]+$ ]] || { echo "invalid child job id: ${job}" >&2; exit 2; }
    job_active "${job}" && active_jobs+=("${job}")
  done
done < "${children}"
if [ -f "${registry}" ]; then
  while IFS=$'\t' read -r _timestamp _kind _seed job _rest; do
    seed_requested "${_seed}" || continue
    job_active "${job:-}" && active_jobs+=("${job}")
  done < "${registry}"
fi
for seed in "${requested_seeds[@]}"; do
  requested_team="${ATTEMPT_DIR}/aar_teams/${AAR_RESUME_TEAM_PREFIX}${seed}${AAR_RESUME_TEAM_SUFFIX}"
  [ -d "${requested_team}" ] || continue
  while IFS= read -r receipt; do
    receipt_job="$(sed -n 's/^job_id=//p' "${receipt}")"
    case "${receipt_job}" in ''|*[!0-9]*) continue;; esac
    job_active "${receipt_job}" && active_jobs+=("${receipt_job}")
  done < <(find "${requested_team}/.train_submissions" -maxdepth 1 \
    -type f -name '*.env' -print 2>/dev/null)
done
if [ "${#active_jobs[@]}" -gt 0 ]; then
  printf 'refusing recovery while attempt job(s) remain active: %s\n' \
    "$(printf '%s\n' "${active_jobs[@]}" | sort -un | tr '\n' ' ')" >&2
  exit 2
fi

declare -A team_by_seed=()
declare -A started_by_seed=()
declare -A remaining_by_seed=()
declare -A resume_uid_by_seed=()
declare -A resume_run_by_seed=()
declare -A repair_proposal_uid_by_seed=()
declare -A retry_train_run_by_seed=()
declare -A retry_train_job_by_seed=()
declare -A retry_train_failure_by_seed=()
declare -a stale_claim_records=()
declare -a stale_eval_timing_records=()

expected_remaining_for() {
  local wanted="$1" item
  for item in ${AAR_RESUME_EXPECTED_REMAINING:-}; do
    case "${item}" in "${wanted}"=*) printf '%s\n' "${item#*=}"; return 0;; esac
  done
  return 1
}

for seed in "${requested_seeds[@]}"; do
  matches="$(awk -F'\t' -v wanted="${seed}" '$1 == wanted {count++; line=$0} END {if (count == 1) print line; else exit 2}' "${children}")" || {
    echo "children.tsv does not contain exactly one row for ${seed}" >&2
    exit 2
  }
  IFS=$'\t' read -r _seed _evaluator _chain <<< "${matches}"
  team_id="${AAR_RESUME_TEAM_PREFIX}${seed}${AAR_RESUME_TEAM_SUFFIX}"
  [[ "${team_id}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "unsafe team id: ${team_id}" >&2; exit 2; }
  team="${ATTEMPT_DIR}/aar_teams/${team_id}"
  [ -d "${team}" ] || { echo "missing team for ${seed}: ${team}" >&2; exit 2; }
  team_by_seed["${seed}"]="${team}"

  started="$(find "${team}/logs" -maxdepth 1 -type f -name "session_*_${seed}_*.log" -print | wc -l | tr -d ' ')"
  [ "${started}" -le "${AAR_RESUME_MAX_SESSIONS}" ] || {
    echo "${seed} has ${started} sessions above ceiling ${AAR_RESUME_MAX_SESSIONS}" >&2
    exit 2
  }
  remaining=$((AAR_RESUME_MAX_SESSIONS - started))
  started_by_seed["${seed}"]="${started}"
  remaining_by_seed["${seed}"]="${remaining}"
  if expected="$(expected_remaining_for "${seed}")"; then
    [ "${remaining}" = "${expected}" ] || {
      echo "${seed} remaining-session mismatch: computed ${remaining}, expected ${expected}" >&2
      exit 2
    }
  fi

  proposal_dir="${team}/scores/.proposals"
  needs_run_id_repair=0
  mapfile -t proposal_markers < <(find "${proposal_dir}" -maxdepth 1 -type f -name '*.json' -print 2>/dev/null | sort)
  latest_proposal=""
  latest_proposal_ts="-1"
  for proposal_marker in "${proposal_markers[@]}"; do
    proposal_ts="$(jq -r 'if (.ts | type) == "number" then .ts else empty end' "${proposal_marker}")"
    [[ "${proposal_ts}" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
      echo "${seed} proposal marker has no numeric timestamp: ${proposal_marker}" >&2
      exit 2
    }
    if awk -v current="${proposal_ts}" -v latest="${latest_proposal_ts}" \
      'BEGIN {exit !(current > latest)}'; then
      latest_proposal="${proposal_marker}"
      latest_proposal_ts="${proposal_ts}"
    elif awk -v current="${proposal_ts}" -v latest="${latest_proposal_ts}" \
      'BEGIN {exit !(current == latest)}'; then
      echo "${seed} has ambiguous proposal markers with timestamp ${proposal_ts}" >&2
      exit 2
    fi
  done
  if [ -n "${latest_proposal}" ] && \
     [ "$(jq -r '.approved // false' "${latest_proposal}")" = true ]; then
    idea_uid="$(jq -r '.idea_uid // empty' "${latest_proposal}")"
    run_id="$(jq -r '.run_id // empty' "${latest_proposal}")"
    if [[ ! "${idea_uid}" =~ ^[A-Za-z0-9._-]+$ ]] || \
       [ "$(basename -- "${latest_proposal}" .json)" != "${idea_uid}" ]; then
      echo "${seed} approved proposal lacks a safe bound idea_uid" >&2
      exit 2
    fi
    finding=""
    if [ -n "${run_id}" ]; then
      [[ "${run_id}" =~ ^[A-Za-z0-9._-]+$ ]] || {
        echo "${seed} approved proposal has an unsafe run_id" >&2
        exit 2
      }
      finding="${team}/.finding_dedup/runid_${run_id}/post.json"
    fi
    # A durable finding closes this proposal.  Do not bind it to the current
    # method file: a later interrupted session may legitimately have edited
    # that shared file after the completed proposal was published.
    if [ ! -f "${finding}" ]; then
      repair_args=(
        --team-dir "${team}"
        --idea-uid "${idea_uid}"
        --plan-only
      )
      validated_run_id="$("${HARNESS_PY}" \
        "${REPO}/scripts/repair_approved_proposal_run_id.py" \
        "${repair_args[@]}" | tail -n 1)"
      if [ -z "${run_id}" ]; then
        run_id="${validated_run_id}"
        needs_run_id_repair=1
      elif [ "${validated_run_id}" != "${run_id}" ]; then
        echo "${seed} approved proposal run stamp disagrees with its marker" >&2
        exit 2
      fi
      [[ "${run_id}" =~ ^[A-Za-z0-9._-]+$ ]] || {
        echo "${seed} approved proposal lacks a recoverable run_id" >&2
        exit 2
      }
      finding="${team}/.finding_dedup/runid_${run_id}/post.json"
      failure="${team}/scores/${run_id}.failed.json"
      failure_stage=""
      [ ! -f "${failure}" ] || failure_stage="$(jq -r '.stage // empty' "${failure}")"
      if [ ! -f "${failure}" ] || \
         { [ "${failure_stage}" = training ] && \
           [ -f "${team}/.train_submissions/${run_id}.env" ] && \
           [ ! -f "${team}/submissions/${run_id}/.submitted" ]; }; then
        resume_uid_by_seed["${seed}"]="${idea_uid}"
        resume_run_by_seed["${seed}"]="${run_id}"
        if [ "${needs_run_id_repair}" = 1 ]; then
          repair_proposal_uid_by_seed["${seed}"]="${idea_uid}"
        fi
      fi
    fi
  fi

  for claim in "${team}/scores/.claims"/*; do
    [ -d "${claim}" ] || continue
    run_id="$(basename -- "${claim}")"
    [[ "${run_id}" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "unsafe evaluator claim: ${claim}" >&2; exit 2; }
    if [ -f "${team}/scores/${run_id}.json" ] || [ -f "${team}/scores/${run_id}.failed.json" ]; then
      continue
    fi
    [ -f "${team}/submissions/${run_id}/.submitted" ] || {
      echo "unscored claim has no submitted adapter: ${claim}" >&2
      exit 2
    }
    stale_claim_records+=("${seed}|${run_id}|${claim}")
    timing="${team}/_eval_private/timings/${run_id}.eval.jsonl"
    [ ! -e "${timing}" ] || stale_eval_timing_records+=("${seed}|${run_id}|${timing}")
  done

  run_id="${resume_run_by_seed[${seed}]:-}"
  if [ -n "${run_id}" ] && [ -f "${team}/.train_submissions/${run_id}.env" ] && \
     [ ! -f "${team}/submissions/${run_id}/.submitted" ] && \
     [ ! -f "${team}/scores/${run_id}.json" ]; then
    receipt="${team}/.train_submissions/${run_id}.env"
    receipt_run="$(sed -n 's/^run_id=//p' "${receipt}")"
    receipt_job="$(sed -n 's/^job_id=//p' "${receipt}")"
    if [ "${receipt_run}" != "${run_id}" ] || \
       [[ ! "${receipt_job}" =~ ^[0-9]+$ ]]; then
      echo "invalid training receipt for ${seed}/${run_id}" >&2
      exit 2
    fi
    state="$(job_state "${receipt_job}")"
    case "${state}" in
      CANCELLED|NODE_FAIL|PREEMPTED|REVOKED) ;;
      FAILED|OUT_OF_MEMORY|TIMEOUT)
        # This is a real completed failure, not an operator/interruption retry.
        # Preserve its marker and let the replacement chain begin a fresh session.
        unset "resume_uid_by_seed[${seed}]" "resume_run_by_seed[${seed}]"
        continue
        ;;
      *) echo "${seed} training job ${receipt_job} is not terminal/retryable (state=${state:-unknown})" >&2; exit 2;;
    esac
    [ "${AAR_RESUME_RETRY_INTERRUPTED_TRAINING:-0}" = 1 ] || {
      echo "${seed} needs interrupted-training recovery; opt-in is disabled" >&2
      exit 2
    }
    retry_train_run_by_seed["${seed}"]="${run_id}"
    retry_train_job_by_seed["${seed}"]="${receipt_job}"
    failure="${team}/scores/${run_id}.failed.json"
    if [ -f "${failure}" ]; then
      if [ "$(jq -r '.run_id // empty' "${failure}")" != "${run_id}" ] || \
         [ "$(jq -r '.stage // empty' "${failure}")" != training ]; then
        echo "${seed} interrupted-training failure marker is not safely bound" >&2
        exit 2
      fi
      retry_train_failure_by_seed["${seed}"]="${failure}"
    fi
  fi
done

for seed in "${requested_seeds[@]}"; do
  [ "${remaining_by_seed[${seed}]}" -gt 0 ] || {
    echo "[resume] ${seed}: session ceiling already exhausted" >&2
    exit 2
  }
done

if [ "${AAR_RESUME_PLAN_ONLY:-0}" = 1 ]; then
  for seed in "${requested_seeds[@]}"; do
    printf '[resume-plan] %s: started=%s remaining=%s resume_run_id=%s retry_training_job=%s\n' \
      "${seed}" "${started_by_seed[${seed}]}" "${remaining_by_seed[${seed}]}" \
      "${resume_run_by_seed[${seed}]:-none}" "${retry_train_job_by_seed[${seed}]:-none}"
  done
  printf '[resume-plan] stale_claims=%s stale_eval_timings=%s; no state changed\n' \
    "${#stale_claim_records[@]}" "${#stale_eval_timing_records[@]}"
  exit 0
fi

recovery_stamp="$(TZ=America/Los_Angeles date '+%Y%m%dT%H%M%S%z')"
archive_root="${ATTEMPT_DIR}/metadata/recovery_archive/${recovery_stamp}"
mkdir -p "${archive_root}"
touch "${registry}"
recovery_commit="$(git -C "${REPO}" rev-parse HEAD)"
record_event() {
  local kind="$1" seed="$2" job="$3" details="$4"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(TZ=America/Los_Angeles date '+%Y-%m-%dT%H:%M:%S%z')" \
    "${kind}" "${seed}" "${job}" "${recovery_commit}" "${details}" >> "${registry}"
}
record_event recovery_start - - \
  "original_commit=${original_commit};config_sha256=${AAR_RESUME_CONFIG_SHA256:-unknown};seeds=${REQUESTED_SEEDS// /,}"

for seed in "${requested_seeds[@]}"; do
  idea_uid="${repair_proposal_uid_by_seed[${seed}]:-}"
  [ -n "${idea_uid}" ] || continue
  team="${team_by_seed[${seed}]}"
  repaired_run_id="$("${HARNESS_PY}" \
    "${REPO}/scripts/repair_approved_proposal_run_id.py" \
    --team-dir "${team}" --idea-uid "${idea_uid}" | tail -n 1)"
  [ "${repaired_run_id}" = "${resume_run_by_seed[${seed}]}" ] || {
    echo "${seed} proposal run-id repair diverged from its validated plan" >&2
    exit 2
  }
  record_event proposal_run_id_repaired "${seed}" - \
    "idea_uid=${idea_uid};run_id=${repaired_run_id}"
done

for record in "${stale_claim_records[@]}"; do
  IFS='|' read -r seed run_id claim <<< "${record}"
  destination="${archive_root}/${seed}/eval_claims/${run_id}"
  mkdir -p "$(dirname -- "${destination}")"
  mv -- "${claim}" "${destination}"
  record_event claim_retired "${seed}" - "run_id=${run_id};archive=${destination}"
done
for record in "${stale_eval_timing_records[@]}"; do
  IFS='|' read -r seed run_id timing <<< "${record}"
  destination="${archive_root}/${seed}/eval_timings/$(basename -- "${timing}")"
  mkdir -p "$(dirname -- "${destination}")"
  mv -- "${timing}" "${destination}"
  record_event eval_timing_retired "${seed}" - "run_id=${run_id};archive=${destination}"
done

for seed in "${requested_seeds[@]}"; do
  run_id="${retry_train_run_by_seed[${seed}]:-}"
  [ -n "${run_id}" ] || continue
  team="${team_by_seed[${seed}]}"
  train_archive="${archive_root}/${seed}/training/${run_id}"
  mkdir -p "${train_archive}"
  receipt="${team}/.train_submissions/${run_id}.env"
  mv -- "${receipt}" "${train_archive}/receipt.env"
  for source in "${team}/_train/${run_id}" "${team}/_train/${run_id}.preflight"; do
    [ ! -e "${source}" ] || mv -- "${source}" "${train_archive}/$(basename -- "${source}")"
  done
  timing="${team}/timings/${run_id}.research.jsonl"
  [ ! -e "${timing}" ] || mv -- "${timing}" "${train_archive}/$(basename -- "${timing}")"
  failure="${retry_train_failure_by_seed[${seed}]:-}"
  [ -z "${failure}" ] || mv -- "${failure}" "${train_archive}/prior_failure.json"
  record_event training_attempt_retired "${seed}" "${retry_train_job_by_seed[${seed}]}" \
    "run_id=${run_id};archive=${train_archive}"
done

for seed in "${requested_seeds[@]}"; do
  team="${team_by_seed[${seed}]}"
  team_id="$(basename -- "${team}")"
  unset AAR_IDEA_UID_OVERRIDE AAR_RESUME_APPROVED_PROPOSAL
  export TEAM_DIR="${team}" TEAM_ID="${team_id}" AAR_TEAM_ID="${team_id}"
  export LOCAL_FINDINGS_DIR="${team}/forum" SUBMISSIONS_DIR="${team}/submissions"
  export SCORES_DIR="${team}/scores" AAR_IDEAS_DIR="${team}/methods"
  export SESSION_LOGS_DIR="${team}/logs" LIT_FORUM_DIR="${team}/litreview"

  eval_log="${ATTEMPT_DIR}/metadata/recovery_eval_${seed}_${recovery_stamp}.txt"
  "${REPO}/scripts/launch_eval_worker.sh" "${SUITE_NAME}" "${AAR_EVAL_IDLE_SECONDS}" 1 \
    | tee "${eval_log}"
  evaluator="$(awk '/^\[launch\] evaluator 1\/1 -> job [0-9]+$/{print $NF}' "${eval_log}")"
  [[ "${evaluator}" =~ ^[0-9]+$ ]] || { echo "missing evaluator job for ${seed}" >&2; exit 2; }
  record_event evaluator "${seed}" "${evaluator}" "team=${team_id}"

  if [ -n "${resume_uid_by_seed[${seed}]:-}" ]; then
    export AAR_IDEA_UID_OVERRIDE="${resume_uid_by_seed[${seed}]}"
    export AAR_RESUME_APPROVED_PROPOSAL=1
  else
    unset AAR_IDEA_UID_OVERRIDE AAR_RESUME_APPROVED_PROPOSAL
  fi
  remaining="${remaining_by_seed[${seed}]}"
  [ "${AAR_CHAIN_SANITIZE_ENV:-0}" = 1 ] || {
    echo "refusing unsanitized research-chain recovery" >&2
    exit 2
  }
  chain_export_names=()
  for chain_name in "${AAR_RESEARCH_CHAIN_ENV_ALLOWLIST[@]}"; do
    case "${chain_name}" in
      HARNESS_ENV|ANTHROPIC_API_KEY|ANT_high_prio_API|ANT_API_KEY|MODEL_API_KEY|LLAMA_API_KEY|HF_TOKEN|HUGGING_FACE_HUB_TOKEN|OAI_API|OPENAI_API_KEY)
        echo "research-chain allowlist contains forbidden credential: ${chain_name}" >&2
        exit 2
        ;;
    esac
    [[ -v "${chain_name}" ]] && chain_export_names+=("${chain_name}")
  done
  for required_export in AAR_REPO AAR_RUNTIME_ROOT TEAM_DIR AAR_AUTODATA \
    AAR_NO_LOCAL_GPU \
    AAR_TARGET_SUCCESSFUL_ITERATIONS AAR_REQUIRE_TRAIN_RECEIPT; do
    [[ " ${chain_export_names[*]} " = *" ${required_export} "* ]] || {
      echo "research-chain export is missing ${required_export}" >&2
      exit 2
    }
  done
  if [ -n "${resume_uid_by_seed[${seed}]:-}" ]; then
    for required_export in AAR_IDEA_UID_OVERRIDE AAR_RESUME_APPROVED_PROPOSAL; do
      [[ " ${chain_export_names[*]} " = *" ${required_export} "* ]] || {
        echo "approved-run recovery export is missing ${required_export}" >&2
        exit 2
      }
    done
  fi
  [ "${#chain_export_names[@]}" -gt 0 ] || {
    echo "sanitized research-chain export allowlist is empty" >&2
    exit 2
  }
  chain_export_csv="$(IFS=,; printf '%s' "${chain_export_names[*]}")"
  chain="$(sbatch --parsable \
    --account="${AAR_SLURM_ACCOUNT:?missing Slurm account}" \
    --partition="${AAR_SLURM_PARTITION:?missing Slurm partition}" \
    --qos="${AAR_AGENT_QOS:?missing agent QoS}" \
    --time="${AAR_RESUME_HOURS}:30:00" \
    --job-name="${AAR_RESUME_JOB_PREFIX}-${seed}-resume" \
    --output="${team}/logs/%x_%j.out" \
    --export="${chain_export_csv}" \
    "${REPO}/scripts/slurm_aar_chain.sh" "explore-${seed}" \
    "${AAR_RESUME_HOURS}" "${remaining}" "${team_id}")"
  chain="${chain%%;*}"
  [[ "${chain}" =~ ^[0-9]+$ ]] || { echo "invalid chain job id for ${seed}: ${chain}" >&2; exit 2; }
  details="team=${team_id};started=${started_by_seed[${seed}]};remaining=${remaining}"
  [ -z "${resume_run_by_seed[${seed}]:-}" ] || \
    details="${details};resume_run_id=${resume_run_by_seed[${seed}]}"
  record_event chain "${seed}" "${chain}" "${details}"
  echo "[resume] ${seed}: ${started_by_seed[${seed}]}/${AAR_RESUME_MAX_SESSIONS} started; evaluator=${evaluator}; chain=${chain}; remaining=${remaining}"
done

echo "[resume] preserved attempt=${ATTEMPT_DIR}; archive=${archive_root}; registry=${registry}"
