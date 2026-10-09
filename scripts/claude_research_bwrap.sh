#!/bin/bash
# Execute the Claude Code research subprocess in a fail-closed mount/PID
# namespace. The trusted Python parent stays outside this namespace so its
# integrity monitor and other services can retain purpose-specific credentials.
# Claude Bash gets the checkout, run artifacts, and an optional pinned AutoData
# plugin, but not the user's remaining home, operator env files, or run secrets.

set -euo pipefail

fail() {
  echo "claude_research_bwrap: $*" >&2
  exit 2
}

[ "${AAR_RESEARCH_ENV_ISOLATION:-0}" = 1 ] || \
  fail "AAR_RESEARCH_ENV_ISOLATION=1 is required"
command -v bwrap >/dev/null || fail "bwrap is required"

real_cli="${AAR_CLAUDE_REAL_CLI_PATH:?missing real Claude CLI path}"
repo="${AAR_REPO:?missing repository path}"
runtime_root="${AAR_RUNTIME_ROOT:?missing run root}"
sandbox_home="${HOME:?missing HOME}"
storage_home="${AAR_RESEARCH_STORAGE_HOME:-/storage/home/${USER:?missing USER}}"
autodata_plugin_root="${AAR_AUTODATA_PLUGIN_ROOT:-}"
autodata_state="${AAR_AUTODATA_STATE:-}"
research_tool_dir="${AAR_RESEARCH_TOOL_DIR:-}"

[ -x "${real_cli}" ] || fail "real Claude CLI is not executable"
[ -d "${repo}" ] || fail "repository does not exist"
[ -d "${runtime_root}" ] || fail "run root does not exist"

real_cli="$(realpath -e -- "${real_cli}")"
repo="$(realpath -e -- "${repo}")"
runtime_root="$(realpath -e -- "${runtime_root}")"
sandbox_home="$(realpath -e -- "${sandbox_home}")"
if [ -n "${research_tool_dir}" ]; then
  [ -d "${research_tool_dir}" ] || fail "research tool directory does not exist"
  research_tool_dir="$(realpath -e -- "${research_tool_dir}")"
  case "${research_tool_dir}" in
    "${runtime_root}"/*) ;;
    *) fail "research tool directory must be inside the run root" ;;
  esac
  [ -x "${research_tool_dir}/ruff" ] || fail "research tool directory lacks ruff"
fi
if [ -n "${autodata_plugin_root}" ]; then
  [ -d "${autodata_plugin_root}" ] || fail "AutoData plugin does not exist"
  autodata_plugin_root="$(realpath -e -- "${autodata_plugin_root}")"
  [ -f "${autodata_plugin_root}/.claude-plugin/plugin.json" ] || \
    fail "AutoData plugin manifest is missing"
  [ -f "${autodata_plugin_root}/skills/autodata/SKILL.md" ] || \
    fail "AutoData skill is missing"
  [ -f "${autodata_plugin_root}/scripts/autodata.py" ] || \
    fail "AutoData CLI wrapper is missing"
fi

case "${sandbox_home}" in /|/home|/storage|/storage/home) fail "unsafe HOME";; esac

declare -a hidden_roots=("${sandbox_home}")
if [ -d "${storage_home}" ]; then
  storage_home="$(realpath -e -- "${storage_home}")"
  case "${storage_home}" in /|/home|/storage|/storage/home) fail "unsafe storage home";; esac
  [ "${storage_home}" = "${sandbox_home}" ] || hidden_roots+=("${storage_home}")
fi

declare -a bwrap_args=(
  --die-with-parent
  --new-session
  --unshare-pid
  --ro-bind / /
  --proc /proc
  --dev /dev
  --tmpfs /tmp
  --tmpfs /var/tmp
)
# Meta's Claude launcher unpacks its native helper below /var/slurm-tmp on
# compute nodes. The root filesystem is intentionally read-only in this
# namespace, so replace that host directory with a private writable tmpfs. The
# conditional keeps the wrapper portable to hosts that do not provide the
# Slurm-specific mountpoint.
if [ -d /var/slurm-tmp ]; then
  bwrap_args+=(--tmpfs /var/slurm-tmp)
fi
for hidden_root in "${hidden_roots[@]}"; do
  bwrap_args+=(--tmpfs "${hidden_root}")
done
bwrap_args+=(--setenv HOME "${sandbox_home}" --setenv TMPDIR /tmp)
if [ -n "${research_tool_dir}" ]; then
  bwrap_args+=(
    --setenv PATH "${research_tool_dir}:${PATH}"
    --setenv AAR_METHOD_VALIDATOR_PY /usr/bin/python3
  )
fi
declare -A made_dirs=()

# A tmpfs over each possible home root removes all original descendants.
# Recreate only the mountpoint hierarchy needed for an approved bind.
add_hidden_mountpoint() {
  local destination="$1" root="" candidate relative component current
  for candidate in "${hidden_roots[@]}"; do
    case "${destination}" in
      "${candidate}"/*)
        # Prefer a nested/more-specific hidden root if roots ever overlap.
        [ "${#candidate}" -gt "${#root}" ] && root="${candidate}"
        ;;
    esac
  done
  [ -n "${root}" ] || return
  relative="${destination#"${root}"/}"
  current="${root}"
  IFS=/ read -r -a components <<< "${relative}"
  for component in "${components[@]}"; do
    [ -n "${component}" ] || continue
    current="${current}/${component}"
    if [[ ! -v "made_dirs[${current}]" ]]; then
      bwrap_args+=(--dir "${current}")
      made_dirs["${current}"]=1
    fi
  done
}

bind_visible_dir() {
  local source="$1" mode="$2"
  add_hidden_mountpoint "${source}"
  if [ "${mode}" = rw ]; then
    bwrap_args+=(--bind "${source}" "${source}")
  else
    bwrap_args+=(--ro-bind "${source}" "${source}")
  fi
}

# The source checkout is an immutable input to the research subprocess. Generated
# methods belong under the retained run's TEAM_DIR, never in the checkout.
bind_visible_dir "${repo}" ro
case "${runtime_root}" in
  "${repo}") fail "runtime root must not equal the read-only source checkout" ;;
  "${repo}"/*) fail "runtime root must not be nested in the read-only source checkout" ;;
  *) bind_visible_dir "${runtime_root}" rw ;;
esac

# The orchestration-owned supervisor keeps the hot native state on the Slurm
# node.  Expose only that one directory at a run-scoped alias; /tmp itself stays
# private to the research sandbox.  The trusted parent continues using the host
# path, while agent CLI status/action calls use the alias to the same inode.
if [ -n "${autodata_state}" ]; then
  autodata_state_root="$(dirname -- "${autodata_state}")"
  [ -d "${autodata_state_root}" ] || fail "AutoData live-state directory is missing"
  autodata_state_root="$(realpath -e -- "${autodata_state_root}")"
  autodata_state_visible="${runtime_root}/autodata/live-state"
  mkdir -p "${autodata_state_visible}"
  bwrap_args+=(
    --bind "${autodata_state_root}" "${autodata_state_visible}"
    --setenv AAR_AUTODATA_STATE "${autodata_state_visible}/$(basename -- "${autodata_state}")"
  )
fi

# The trusted parent has already verified the plugin's checkout, branch, SHA,
# manifest, and symlink policy. Restore only that plugin directory read-only;
# never expose the rest of the otherwise hidden user home.
if [ -n "${autodata_plugin_root}" ]; then
  case "${autodata_plugin_root}" in
    "${repo}"|"${repo}"/*|"${runtime_root}"|"${runtime_root}"/*) ;;
    *) bind_visible_dir "${autodata_plugin_root}" ro ;;
  esac
  bwrap_args+=(
    --setenv AAR_AUTODATA_PLUGIN_ROOT "${autodata_plugin_root}"
    --setenv AUTODATA_CACHE_DIR "${runtime_root}/autodata/plugin-cache"
  )
fi

# Worktree Git metadata commonly lives in a sibling checkout hidden by the
# HOME tmpfs.  Restore only the Git database, read-only, rather than its parent.
git_common=""
if [ -e "${repo}/.git" ]; then
  git_common="$(git -C "${repo}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
fi
if [ -n "${git_common}" ] && [ -d "${git_common}" ]; then
  git_common="$(realpath -e -- "${git_common}")"
  case "${git_common}" in
    "${repo}"|"${repo}"/*|"${runtime_root}"|"${runtime_root}"/*) ;;
    *) bind_visible_dir "${git_common}" ro ;;
  esac
fi

# A home-installed Claude binary may have adjacent runtime files.  Restore its
# containing directory read-only.  System installations remain in the root
# read-only view and need no extra mount.
cli_dir="$(dirname -- "${real_cli}")"
for hidden_root in "${hidden_roots[@]}"; do
  case "${cli_dir}" in
    "${hidden_root}"|"${hidden_root}"/*)
    case "${cli_dir}" in
      "${repo}"|"${repo}"/*|"${runtime_root}"|"${runtime_root}"/*) ;;
      *) bind_visible_dir "${cli_dir}" ro ;;
    esac
    break
    ;;
  esac
done

# The Meta launcher is system-owned, but its versioned DotSlash descriptor and
# already-materialized native binary live in two non-secret user cache trees.
# The HOME tmpfs would otherwise hide them and force a Manifold download through
# shared host scratch. Expose only these caches read-only; give DotSlash a
# private lock directory and require an offline cache hit. No Claude settings,
# sessions, shell state, or general user cache becomes visible.
claude_native_cache="${sandbox_home}/.cache/claude_code_native_versions"
dotslash_cache="${sandbox_home}/.cache/dotslash"
if [ -d "${claude_native_cache}" ] && [ -d "${dotslash_cache}" ]; then
  bind_visible_dir "${claude_native_cache}" ro
  bind_visible_dir "${dotslash_cache}" ro
  if [ -d "${dotslash_cache}/locks" ]; then
    bwrap_args+=(--tmpfs "${dotslash_cache}/locks")
  fi
  bwrap_args+=(--setenv DOTSLASH_OFFLINE 1)
fi

# Rebinding the checkout/run also restores their credential files, so mask
# those last. /dev/null preserves a harmless file-shaped mountpoint without
# exposing content; the secret directory becomes an empty private tmpfs.
for masked_file in \
  "${repo}/.env" \
  "${repo}/.sandoq-firecracker-token" \
  /opt/aar/eval-user/.env; do
  [ -e "${masked_file}" ] || continue
  bwrap_args+=(--ro-bind /dev/null "${masked_file}")
done
if [ -d "${runtime_root}/secrets" ]; then
  bwrap_args+=(--tmpfs "${runtime_root}/secrets")
fi
# Same-UID functional evaluation state is additionally hidden from the research
# namespace. The evaluator remains outside this mount namespace.
for eval_private in \
  "${runtime_root}/eval/holdout" \
  "${TEAM_DIR:-${runtime_root}/aar_teams/unknown}/_eval_private"; do
  if [ -d "${eval_private}" ]; then
    bwrap_args+=(--tmpfs "${eval_private}")
  fi
done

# Do not reveal wrapper-control values to Claude.  The SDK-side spawn guard has
# already removed raw keys/token paths; repeat the rule here so this boundary
# remains fail-closed if a future caller bypasses the Python helper.
unset AAR_CLAUDE_REAL_CLI_PATH AAR_RESEARCH_STORAGE_HOME
# A version override makes Meta's launcher download and unpack another native
# binary below the host Slurm scratch tree. That path is deliberately hidden by
# this sandbox, and the launcher itself recommends using its installed native
# version when the override cannot be materialized. Keep the trusted launcher
# but prevent an operator-side pin from crossing this isolation boundary.
unset META_CLAUDE_CODE_RELEASE CLAUDE_CODE_VERSION_OVERRIDE
unset git_common cli_dir masked_file hidden_root storage_home autodata_plugin_root eval_private
unset autodata_state autodata_state_root autodata_state_visible
unset claude_native_cache dotslash_cache
unset research_tool_dir
while IFS= read -r env_name; do
  upper_name="${env_name^^}"
  case "${upper_name}" in
    AAR_AUTODATA_CAPABILITY) continue ;;
    AAR_AUTODATA_EXECSIDECAR_TOKEN_FILE|AAR_AUTODATA_MODEL_ENV_FILE|AAR_AUTODATA_APPROVAL_PRIVATE_KEY|HARNESS_ENV|ANTHROPIC_API_KEY|ANT_HIGH_PRIO_API|ANT_API_KEY|MODEL_API_KEY|LLAMA_API_KEY|HF_TOKEN|HUGGING_FACE_HUB_TOKEN|OAI_API|OPENAI_API_KEY|*_API_KEY|*_TOKEN|*_TOKEN_FILE|*_SECRET|*_SECRET_FILE|*CREDENTIAL*)
      unset "${env_name}"
      ;;
  esac
done < <(compgen -e)
unset env_name upper_name

exec bwrap "${bwrap_args[@]}" -- "${real_cli}" "$@"
