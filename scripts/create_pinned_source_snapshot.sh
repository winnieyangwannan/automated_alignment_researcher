#!/bin/bash
# Create an independent detached clone for one durable run attempt.
set -euo pipefail
umask 077

SOURCE_REPO="${1:?usage: create_pinned_source_snapshot.sh SOURCE_REPO COMMIT DESTINATION}"
EXPECTED_COMMIT="${2:?usage: create_pinned_source_snapshot.sh SOURCE_REPO COMMIT DESTINATION}"
DESTINATION="${3:?usage: create_pinned_source_snapshot.sh SOURCE_REPO COMMIT DESTINATION}"

SOURCE_REPO="$(realpath -e -- "${SOURCE_REPO}")"
[[ "${EXPECTED_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "source snapshot requires a full lowercase commit SHA" >&2
  exit 2
}
[ "$(git -C "${SOURCE_REPO}" rev-parse "${EXPECTED_COMMIT}^{commit}")" = "${EXPECTED_COMMIT}" ] || {
  echo "source snapshot commit is unavailable" >&2
  exit 2
}

destination_parent="$(dirname -- "${DESTINATION}")"
destination_name="$(basename -- "${DESTINATION}")"
mkdir -p -- "${destination_parent}"
destination_parent="$(realpath -e -- "${destination_parent}")"
case "${destination_name}" in
  ''|.|..) echo "source snapshot destination is unsafe" >&2; exit 2 ;;
esac
DESTINATION="${destination_parent}/${destination_name}"
[ ! -e "${DESTINATION}" ] || {
  echo "source snapshot destination already exists" >&2
  exit 2
}

temporary="$(mktemp -d "${destination_parent}/.source-snapshot.XXXXXX")"
cleanup() {
  if [ -n "${temporary:-}" ] && [ -d "${temporary}" ]; then
    rm -rf -- "${temporary}"
  fi
}
trap cleanup EXIT

# --no-local gives the attempt its own object database rather than hardlinks or
# an alternates pointer into the mutable shared checkout.
git clone --quiet --no-local --no-checkout -- "${SOURCE_REPO}" "${temporary}"
git -C "${temporary}" checkout --quiet --detach "${EXPECTED_COMMIT}"
git -C "${temporary}" remote remove origin
[ "$(git -C "${temporary}" rev-parse HEAD)" = "${EXPECTED_COMMIT}" ] || {
  echo "source snapshot checkout drifted" >&2
  exit 2
}
[ -z "$(git -C "${temporary}" branch --show-current)" ] || {
  echo "source snapshot is not detached" >&2
  exit 2
}
git -C "${temporary}" diff --quiet
git -C "${temporary}" diff --cached --quiet
[ ! -e "${temporary}/.git/objects/info/alternates" ] || {
  echo "source snapshot unexpectedly depends on shared Git objects" >&2
  exit 2
}

mv -- "${temporary}" "${DESTINATION}"
temporary=""
trap - EXIT
printf '%s\n' "${DESTINATION}"
