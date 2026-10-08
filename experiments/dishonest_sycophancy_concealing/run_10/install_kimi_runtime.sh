#!/bin/bash
# Install the pinned official Kimi Code CLI in an HPC-local ARM64 runtime.
set -euo pipefail
umask 077

NODE_VERSION=22.22.0
NODE_ARCHIVE="node-v${NODE_VERSION}-linux-arm64.tar.xz"
NODE_SHA256=1bf1eb9ee63ffc4e5d324c0b9b62cf4a289f44332dfef9607cea1a0d9596ba6f
KIMI_VERSION=2.1.1
KIMI_TARBALL_SHA256=6690a29d7b5e14812754dd100136b7f4ee2577add8895f00fe27025b4412049f
TOOLS_ROOT="${AAR_RUN10_TOOLS_ROOT:-/storage/home/${USER:?}/tools}"
NODE_ROOT="${TOOLS_ROOT}/node-v${NODE_VERSION}-linux-arm64"
KIMI_ROOT="${TOOLS_ROOT}/kimi-code-${KIMI_VERSION}"

[ "$(uname -m)" = aarch64 ] || { echo "Kimi runtime installer requires aarch64" >&2; exit 2; }
mkdir -p "${TOOLS_ROOT}"
stage="$(mktemp -d "${TOOLS_ROOT}/.kimi-runtime.XXXXXX")"
cleanup() { rm -rf --one-file-system -- "${stage}"; }
trap cleanup EXIT

if [ ! -x "${NODE_ROOT}/bin/node" ]; then
  curl --fail --location --retry 3 \
    "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_ARCHIVE}" \
    --output "${stage}/${NODE_ARCHIVE}"
  printf '%s  %s\n' "${NODE_SHA256}" "${stage}/${NODE_ARCHIVE}" | sha256sum -c -
  tar -xJf "${stage}/${NODE_ARCHIVE}" -C "${stage}"
  mv -- "${stage}/node-v${NODE_VERSION}-linux-arm64" "${NODE_ROOT}"
fi
[ "$("${NODE_ROOT}/bin/node" --version)" = "v${NODE_VERSION}" ] || {
  echo "unexpected Node version" >&2
  exit 2
}

if [ ! -x "${KIMI_ROOT}/node_modules/.bin/kimi" ]; then
  mkdir "${stage}/kimi"
  printf '{"private":true,"dependencies":{"@moonshot-ai/kimi-code":"%s"}}\n' \
    "${KIMI_VERSION}" > "${stage}/kimi/package.json"
  (
    cd -- "${stage}/kimi"
    PATH="${NODE_ROOT}/bin:${PATH}" npm install --ignore-scripts=false --include=optional \
      --save-exact --package-lock=true
    tarball="$(PATH="${NODE_ROOT}/bin:${PATH}" npm pack --silent @moonshot-ai/kimi-code@${KIMI_VERSION})"
    [ "$(sha256sum "${tarball}" | awk '{print $1}')" = "${KIMI_TARBALL_SHA256}" ] || {
      echo "Kimi package tarball hash mismatch" >&2
      exit 2
    }
    rm -- "${tarball}"
  )
  mv -- "${stage}/kimi" "${KIMI_ROOT}"
fi

PATH="${NODE_ROOT}/bin:${PATH}" "${KIMI_ROOT}/node_modules/.bin/kimi" --version
(
  cd -- "${KIMI_ROOT}"
  "${NODE_ROOT}/bin/node" -e 'require("node-pty"); console.log("node-pty ok")'
)
sha256sum "${KIMI_ROOT}/package-lock.json"
printf 'KIMI_CLI_PATH=%s\nNODE_ROOT=%s\n' \
  "${KIMI_ROOT}/node_modules/.bin/kimi" "${NODE_ROOT}"
