#!/bin/bash
# Source-only helper for validating retained Run 15 recovery configurations.

run15_recovery_config_compatible() {
  local retained="$1" canonical="$2" normalized_retained="" normalized_canonical=""
  local source="" destination="" result=1
  cmp -s -- "${retained}" "${canonical}" && return 0
  [ "$(grep -c '^  vllm_log_stats: true$' "${canonical}")" = 1 ] || return 1
  [ "$(grep -c '^  adapter_retention: all$' "${canonical}")" = 1 ] || return 1
  [ "$(grep -c '^  continuation_exhaustion_retryable: true$' "${canonical}")" = 1 ] || return 1
  normalized_retained="$(mktemp)"
  normalized_canonical="$(mktemp)"
  for source in "${retained}" "${canonical}"; do
    destination="${normalized_retained}"
    [ "${source}" = "${canonical}" ] && destination="${normalized_canonical}"
    sed \
      -e '/^  # Retain every final LoRA, while pruning Trainer checkpoints and tokenizer copies\.$/d' \
      -e '/^  adapter_retention: all$/d' \
      -e '/^  # Emit vLLM scheduler throughput, request, prefix-cache, and KV-cache stats\.$/d' \
      -e '/^  vllm_log_stats: true$/d' \
    -e '/^  # A full five-chain run must advance to a fresh session when one Kimi$/d' \
    -e '/^  # conversation exhausts its bounded continuation budget\.$/d' \
    -e '/^  continuation_exhaustion_retryable: true$/d' \
    -e '/^  max_continuations: 32$/d' \
    -e '/^  progress_stall_limit: 3$/d' \
    -e '/^  progress_stall_grace_continuations: 8$/d' \
      "${source}" | awk '
        /^recovery:$/ { skip=1; next }
        skip && /^[^[:space:]#]/ { skip=0 }
        !skip { print }
      ' > "${destination}"
  done
  cmp -s -- "${normalized_retained}" "${normalized_canonical}" && result=0
  rm -f -- "${normalized_retained}" "${normalized_canonical}"
  return "${result}"
}
