#!/usr/bin/env bash

set -u

DEFAULT_CLUSTER="fair-cw-use2-1"
RETRY_SECONDS="${FAIR_HPC_TUNNEL_RETRY_SECONDS:-20}"
CONNECT_TIMEOUT="${FAIR_HPC_TUNNEL_CONNECT_TIMEOUT:-600}"
JUMP_CONNECT_TIMEOUT="${FAIR_HPC_TUNNEL_JUMP_CONNECT_TIMEOUT:-180}"
SERVER_ALIVE_INTERVAL="${FAIR_HPC_TUNNEL_SERVER_ALIVE_INTERVAL:-30}"
SERVER_ALIVE_COUNT_MAX="${FAIR_HPC_TUNNEL_SERVER_ALIVE_COUNT_MAX:-10}"

usage() {
    cat <<'EOF'
Usage: fair_hpc_tunnel.sh <start|status|attach|worker> [cluster]

  start   Start a persistent tunnel in a detached tmux session.
  status  Check the listener and verify the configured SSH alias.
  attach  Attach to the tunnel's tmux session (needed for Duo prompts).
  worker  Internal reconnect loop run inside tmux.

The worker obtains the current bastion and login endpoint from
`cloud hpc port-forward` before every connection attempt. It never stores
credentials or hard-codes an ephemeral endpoint.
EOF
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

session_name() {
    local cluster="$1"
    printf 'fair-hpc-tunnel-%s\n' "${cluster//[^A-Za-z0-9_-]/-}"
}

ssh_config_value() {
    local cluster="$1"
    local key="$2"
    ssh -G "$cluster" 2>/dev/null | awk -v wanted="$key" '$1 == wanted { print $2; exit }'
}

configured_port() {
    local port
    port="$(ssh_config_value "$1" port)"
    [[ "$port" =~ ^[0-9]+$ ]] || die "could not resolve a numeric SSH port for $1"
    printf '%s\n' "$port"
}

cluster_identity() {
    local cluster="$1"
    local user candidate expanded
    user="$(ssh_config_value "$cluster" user)"
    while read -r candidate; do
        expanded="${candidate/#\~/$HOME}"
        expanded="${expanded//%u/$user}"
        if [[ -f "$expanded" ]]; then
            printf '%s\n' "$expanded"
            return 0
        fi
    done < <(ssh -G "$cluster" 2>/dev/null | awk '$1 == "identityfile" { print $2 }')
    die "no configured identity file exists for $cluster"
}

has_listener() {
    local port="$1"
    ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .
}

status_tunnel() {
    local cluster="$1"
    local host port
    host="$(ssh_config_value "$cluster" hostname)"
    port="$(configured_port "$cluster")"
    case "$host" in
        localhost|127.0.0.1|::1) ;;
        *) die "$cluster resolves to $host, not a local tunnel" ;;
    esac

    if ! has_listener "$port"; then
        printf '%s: no listener on localhost:%s\n' "$cluster" "$port"
        return 1
    fi

    printf '%s: listener is present on localhost:%s\n' "$cluster" "$port"
    if ssh -o BatchMode=yes -o ConnectTimeout=15 "$cluster" 'hostname' 2>/dev/null; then
        printf '%s: SSH alias verified\n' "$cluster"
        return 0
    fi
    printf '%s: listener exists, but SSH alias verification failed\n' "$cluster" >&2
    return 1
}

parse_forward_targets() {
    local output="$1"
    local jump target
    jump="$(printf '%s\n' "$output" | sed -n 's/^[[:space:]]*-J[[:space:]]\([^[:space:]]*\).*/\1/p' | tail -1)"
    target="$(printf '%s\n' "$output" | awk '
        /^[[:space:]]+[A-Za-z0-9._-]+@[A-Za-z0-9.-]+[[:space:]]*$/ {
            gsub(/^[[:space:]]+|[[:space:]]+$/, ""); target=$0
        }
        END { print target }
    ')"
    [[ "$jump" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$ ]] || return 1
    [[ "$target" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$ ]] || return 1
    printf '%s\n%s\n' "$jump" "$target"
}

run_worker() {
    local cluster="$1"
    local port identity forward_output jump target proxy_command rc
    port="$(configured_port "$cluster")"
    identity="$(cluster_identity "$cluster")"

    while true; do
        if has_listener "$port"; then
            printf '[%s] localhost:%s is already in use; retrying in %ss\n' \
                "$(date --iso-8601=seconds)" "$port" "$RETRY_SECONDS"
            sleep "$RETRY_SECONDS"
            continue
        fi

        printf '[%s] resolving current endpoint for %s\n' "$(date --iso-8601=seconds)" "$cluster"
        if ! forward_output="$(cloud hpc port-forward "$cluster" 22 \
            --local-port "$port" --no-vpnless --no-et 2>&1)"; then
            printf '%s\n' "$forward_output" >&2
            printf '[%s] endpoint lookup failed; retrying in %ss\n' \
                "$(date --iso-8601=seconds)" "$RETRY_SECONDS" >&2
            sleep "$RETRY_SECONDS"
            continue
        fi

        mapfile -t targets < <(parse_forward_targets "$forward_output")
        if [[ "${#targets[@]}" -ne 2 ]]; then
            printf '%s\n' "$forward_output" >&2
            printf '[%s] could not parse forwarding targets; retrying in %ss\n' \
                "$(date --iso-8601=seconds)" "$RETRY_SECONDS" >&2
            sleep "$RETRY_SECONDS"
            continue
        fi
        jump="${targets[0]}"
        target="${targets[1]}"
        proxy_command="ssh -i $identity -o IdentitiesOnly=yes -o ConnectTimeout=$JUMP_CONNECT_TIMEOUT -o StrictHostKeyChecking=accept-new -W %h:%p $jump"

        printf '[%s] connecting %s (Duo may require approval)\n' \
            "$(date --iso-8601=seconds)" "$cluster"
        ssh \
            -i "$identity" \
            -o IdentitiesOnly=yes \
            -o "ProxyCommand=$proxy_command" \
            -o StrictHostKeyChecking=accept-new \
            -o PasswordAuthentication=no \
            -o "ServerAliveInterval=$SERVER_ALIVE_INTERVAL" \
            -o "ServerAliveCountMax=$SERVER_ALIVE_COUNT_MAX" \
            -o "ConnectTimeout=$CONNECT_TIMEOUT" \
            -o ConnectionAttempts=3 \
            -o ExitOnForwardFailure=yes \
            -N -T \
            -L "localhost:$port:localhost:22" \
            "$target"
        rc=$?
        printf '[%s] tunnel exited with status %s; retrying in %ss\n' \
            "$(date --iso-8601=seconds)" "$rc" "$RETRY_SECONDS" >&2
        sleep "$RETRY_SECONDS"
    done
}

start_tunnel() {
    local cluster="$1"
    local session port
    session="$(session_name "$cluster")"
    port="$(configured_port "$cluster")"

    if tmux has-session -t "=$session" 2>/dev/null; then
        printf 'tmux session %s is already running\n' "$session"
        return 0
    fi
    if has_listener "$port"; then
        printf 'localhost:%s already has a listener; leaving it unchanged\n' "$port"
        printf 'Run status now. Stop the old tunnel before starting this supervised one.\n'
        return 0
    fi

    tmux new-session -d -s "$session" "$(realpath "$0")" worker "$cluster"
    printf 'started tmux session %s\n' "$session"
    printf 'attach for Duo or logs: tmux attach -t %s\n' "$session"
}

command="${1:-}"
cluster="${2:-$DEFAULT_CLUSTER}"
case "$command" in
    start) start_tunnel "$cluster" ;;
    status) status_tunnel "$cluster" ;;
    attach) exec tmux attach -t "$(session_name "$cluster")" ;;
    worker) run_worker "$cluster" ;;
    -h|--help|help|'') usage ;;
    *) usage >&2; exit 2 ;;
esac
