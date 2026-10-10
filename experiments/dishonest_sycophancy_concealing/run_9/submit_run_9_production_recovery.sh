#!/bin/bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
ATTEMPT_DIR="${AAR_RUN_ATTEMPT_DIR:-/storage/home/${USER:?}/aar-runs/run9-five-iteration/20261009T042010Z-9177dca332eb}"
AUTODATA="${AAR_AUTODATA_CHECKOUT:-/storage/home/${USER}/autodata-recovery-clones/run9-823c594-speedup}"
BROKER_PYTHON="${AAR_AUTODATA_BROKER_PYTHON:-/storage/home/${USER}/envs/autodata-broker-py312/bin/python}"
EXECUTION_ID="${AAR_PRODUCTION_EXECUTION_ID:-exe_570e1daeb28c4a7795a2be9fac37fdf9}"
CONCURRENCY="${AAR_AUTODATA_CONCURRENCY:-16}"
MAX_SECONDS="${AAR_SPEEDUP_MAX_SECONDS:-300}"
ATTEMPT_LABEL="${AAR_SPEEDUP_ATTEMPT_LABEL:-attempt-1-node-local-c16}"
EXPECTED_AUTODATA_SHA=823c5948854df14664f3168bc5e6c49a2cecb975

[ "$(git -C "${REPO}" branch --show-current)" = autodata ] || {
  echo "Run 9 production recovery requires AAR branch autodata" >&2
  exit 2
}
git -C "${REPO}" diff --quiet
git -C "${REPO}" diff --cached --quiet
[ "$(git -C "${AUTODATA}" branch --show-current)" = main ] || {
  echo "recovery AutoData checkout must use branch main" >&2
  exit 2
}
[ "$(git -C "${AUTODATA}" rev-parse HEAD)" = "${EXPECTED_AUTODATA_SHA}" ] || {
  echo "recovery AutoData checkout is not pinned to ${EXPECTED_AUTODATA_SHA}" >&2
  exit 2
}
git -C "${AUTODATA}" diff --quiet
git -C "${AUTODATA}" diff --cached --quiet
case "${CONCURRENCY}" in 16|24|32) ;; *) echo "concurrency must be 16, 24, or 32" >&2; exit 2;; esac
case "${MAX_SECONDS}" in ''|*[!0-9]*) echo "max seconds must be a non-negative integer" >&2; exit 2;; esac

aar_sha="$(git -C "${REPO}" rev-parse HEAD)"
logs="${ATTEMPT_DIR}/aar_teams/run9-gemma4-31b-opus48-autodata-five-success-v1/logs/production-speedup"
mkdir -p "${logs}"
chmod 700 "${logs}"
job_id="$(sbatch --parsable \
  --output="${logs}/${ATTEMPT_LABEL}-%j.out" \
  --export="AAR_REPO=${REPO},AAR_RUN_ATTEMPT_DIR=${ATTEMPT_DIR},AAR_AUTODATA_CHECKOUT=${AUTODATA},AAR_AUTODATA_BROKER_PYTHON=${BROKER_PYTHON},AAR_PRODUCTION_EXECUTION_ID=${EXECUTION_ID},AAR_AUTODATA_CONCURRENCY=${CONCURRENCY},AAR_SPEEDUP_MAX_SECONDS=${MAX_SECONDS},AAR_SPEEDUP_ATTEMPT_LABEL=${ATTEMPT_LABEL},AAR_EXPECTED_AAR_SHA=${aar_sha},AAR_EXPECTED_AUTODATA_SHA=${EXPECTED_AUTODATA_SHA}" \
  "${SCRIPT_DIR}/run_9_production_recovery.sbatch")"
record="${logs}/${ATTEMPT_LABEL}-submission.txt"
printf 'job_id=%s\nattempt_label=%s\naar_commit=%s\nautodata_commit=%s\nconcurrency=%s\nmax_seconds=%s\nexecution_id=%s\n' \
  "${job_id}" "${ATTEMPT_LABEL}" "${aar_sha}" "${EXPECTED_AUTODATA_SHA}" \
  "${CONCURRENCY}" "${MAX_SECONDS}" "${EXECUTION_ID}" > "${record}"
printf '%s\n' "${job_id}"
