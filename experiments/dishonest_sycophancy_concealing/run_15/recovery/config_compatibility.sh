#!/bin/bash
# Source-only helper for validating retained Run 15 recovery configurations.

run15_recovery_config_compatible() {
  local retained="$1" canonical="$2" normalized="" result=1
  cmp -s -- "${retained}" "${canonical}" && return 0
  [ "$(grep -c '^  vllm_log_stats: true$' "${canonical}")" = 1 ] || return 1
  normalized="$(mktemp)"
  sed \
    -e '/^  # Emit vLLM scheduler throughput, request, prefix-cache, and KV-cache stats\.$/d' \
    -e '/^  vllm_log_stats: true$/d' \
    "${canonical}" > "${normalized}"
  cmp -s -- "${retained}" "${normalized}" && result=0
  rm -f -- "${normalized}"
  return "${result}"
}
