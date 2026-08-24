#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${OCI_ENV_FILE:-$ROOT_DIR/.env.oci}"

if [ ! -f "$ENV_FILE" ]; then
  echo "missing OCI environment file: $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

OCI_USER="${OCI_USER:-opc}"
OCI_IP="${OCI_IP:-}"
OCI_KEY_PATH="${OCI_KEY_PATH:-$HOME/.ssh/trevor_oci_ed25519}"
OCI_KEY_PATH="${OCI_KEY_PATH/#\~/$HOME}"
OCI_REMOTE_DIR="${OCI_REMOTE_DIR:-/home/$OCI_USER/trevor-app}"
OCI_LOCAL_DIR="${OCI_LOCAL_DIR:-$ROOT_DIR/}"
OCI_LOCAL_DIR="${OCI_LOCAL_DIR%/}/"
OCI_SSH_CONNECT_TIMEOUT="${OCI_SSH_CONNECT_TIMEOUT:-10}"
OCI_SSH_CONNECTION_ATTEMPTS="${OCI_SSH_CONNECTION_ATTEMPTS:-1}"
OCI_SSH_SERVER_ALIVE_INTERVAL="${OCI_SSH_SERVER_ALIVE_INTERVAL:-10}"
OCI_SSH_SERVER_ALIVE_COUNT_MAX="${OCI_SSH_SERVER_ALIVE_COUNT_MAX:-2}"
OCI_SSH_STRICT_HOST_KEY_CHECKING="${OCI_SSH_STRICT_HOST_KEY_CHECKING:-accept-new}"
OCI_SSH_USER_KNOWN_HOSTS_FILE="${OCI_SSH_USER_KNOWN_HOSTS_FILE:-$HOME/.ssh/known_hosts}"
OCI_VERIFY_AFTER_SYNC="${OCI_VERIFY_AFTER_SYNC:-1}"

print_config() {
  printf 'OCI_USER=%s\n' "$OCI_USER"
  printf 'OCI_IP=%s\n' "$OCI_IP"
  printf 'OCI_KEY_PATH=%s\n' "$OCI_KEY_PATH"
  printf 'OCI_REMOTE_DIR=%s\n' "$OCI_REMOTE_DIR"
  printf 'OCI_LOCAL_DIR=%s\n' "$OCI_LOCAL_DIR"
  printf 'OCI_SSH_STRICT_HOST_KEY_CHECKING=%s\n' "$OCI_SSH_STRICT_HOST_KEY_CHECKING"
  printf 'OCI_VERIFY_AFTER_SYNC=%s\n' "$OCI_VERIFY_AFTER_SYNC"
}

if [ "${1:-}" = "--print-config" ]; then
  print_config
  exit 0
fi

MODE="${1:---sync-only}"
case "$MODE" in
  --sync-only|--install-services|--preflight-only)
    ;;
  *)
    echo "usage: $0 [--print-config|--preflight-only|--sync-only|--install-services]" >&2
    exit 2
    ;;
esac

if [ -z "$OCI_IP" ] || [ ! -f "$OCI_KEY_PATH" ]; then
  echo "OCI host or SSH key is unavailable" >&2
  exit 1
fi
chmod 0600 "$OCI_KEY_PATH"

SSH_OPTIONS=(
  -i "$OCI_KEY_PATH"
  -o "IdentitiesOnly=yes"
  -o "BatchMode=yes"
  -o "ConnectTimeout=$OCI_SSH_CONNECT_TIMEOUT"
  -o "ConnectionAttempts=$OCI_SSH_CONNECTION_ATTEMPTS"
  -o "ServerAliveInterval=$OCI_SSH_SERVER_ALIVE_INTERVAL"
  -o "ServerAliveCountMax=$OCI_SSH_SERVER_ALIVE_COUNT_MAX"
  -o "StrictHostKeyChecking=$OCI_SSH_STRICT_HOST_KEY_CHECKING"
  -o "UserKnownHostsFile=$OCI_SSH_USER_KNOWN_HOSTS_FILE"
)
REMOTE="$OCI_USER@$OCI_IP"

if [ "$MODE" = "--preflight-only" ]; then
  ssh "${SSH_OPTIONS[@]}" "$REMOTE" \
    "set -eu; command -v sudo >/dev/null; command -v curl >/dev/null; printf 'remote=ok\\n'; uname -sm"
  echo "preflight=ok"
  exit 0
fi

ssh "${SSH_OPTIONS[@]}" "$REMOTE" "mkdir -p '$OCI_REMOTE_DIR'"
rsync -a \
  --exclude '.env' --exclude '.env.*' --exclude '.venv*' \
  --exclude 'data/' --exclude 'data_hdd_storage/' --exclude 'logs/' \
  --exclude '__pycache__/' --exclude '*.pyc' \
  -e "ssh ${SSH_OPTIONS[*]}" \
  "$OCI_LOCAL_DIR" "$REMOTE:$OCI_REMOTE_DIR/"

if [ "$MODE" = "--install-services" ]; then
  ssh "${SSH_OPTIONS[@]}" "$REMOTE" \
    "sudo bash '$OCI_REMOTE_DIR/deploy/systemd/install.sh' '$OCI_REMOTE_DIR'"
fi

if [ "$OCI_VERIFY_AFTER_SYNC" = "1" ]; then
  ssh "${SSH_OPTIONS[@]}" "$REMOTE" \
    "cd '$OCI_REMOTE_DIR' && git status --short && python3 -m py_compile system_main.py"
fi
