#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi

SOURCE_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
APP_ROOT="/opt/trevor/app"
DATA_ROOT="/var/lib/trevor"
CONFIG_ROOT="/etc/trevor"
CREDENTIAL_ROOT="$CONFIG_ROOT/credentials"
UV_CACHE_ROOT="$DATA_ROOT/cache/uv"

if [ ! -f "$SOURCE_ROOT/system_main.py" ]; then
  echo "invalid Trevor source root" >&2
  exit 1
fi

ensure_host_tools() {
  if command -v curl >/dev/null 2>&1 && command -v rsync >/dev/null 2>&1; then
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates curl rsync
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl rsync
  else
    echo "supported package manager not found; install curl and rsync" >&2
    exit 1
  fi
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
  command -v uv >/dev/null 2>&1 || {
    echo "uv installation failed" >&2
    exit 1
  }
}

ensure_host_tools
ensure_uv

if ! id trevor >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/trevor --shell /usr/sbin/nologin trevor
fi

install -d -o trevor -g trevor -m 0700 "$DATA_ROOT" "$UV_CACHE_ROOT"
install -d -o root -g root -m 0755 /opt/trevor "$APP_ROOT" "$CONFIG_ROOT"
install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT"

if [ "$(realpath "$SOURCE_ROOT")" != "$(realpath "$APP_ROOT")" ]; then
  rsync -a --exclude '.venv*' --exclude 'data/' --exclude 'logs/' --exclude '.env*' \
    "$SOURCE_ROOT/" "$APP_ROOT/"
fi
chown -R trevor:trevor "$APP_ROOT"

uv python install 3.12
runuser -u trevor -- env UV_CACHE_DIR="$UV_CACHE_ROOT" \
  uv venv --python 3.12 --clear "$APP_ROOT/.venv"
runuser -u trevor -- env UV_CACHE_DIR="$UV_CACHE_ROOT" \
  uv pip sync --python "$APP_ROOT/.venv/bin/python" "$APP_ROOT/requirements.txt"
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PROJECT_ENVIRONMENT="$APP_ROOT/services/graphiti_sidecar/.venv" \
  uv sync --project "$APP_ROOT/services/graphiti_sidecar" --frozen --no-dev

audit_deployment() {
  local status="$1"
  (
    cd "$APP_ROOT"
    runuser -u trevor -- env TREVOR_DATA_DIR="$DATA_ROOT" \
      "$APP_ROOT/.venv/bin/python" tools/trevor_operations.py audit \
      --event deployment \
      --status "$status" \
      --subject oci-systemd \
      --data-root "$DATA_ROOT"
  )
}

deployment_exit() {
  local exit_code=$?
  if [ "$exit_code" -ne 0 ]; then
    audit_deployment failed >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}

trap deployment_exit EXIT
audit_deployment started

if [ ! -f "$CONFIG_ROOT/trevor.env" ]; then
  install -o root -g root -m 0600 \
    "$APP_ROOT/deploy/systemd/trevor.env.example" "$CONFIG_ROOT/trevor.env"
fi

required_credentials=(
  nvidia_api_key
  graphiti_token
  trevor_api_hmac
  trevor_memory_key_b64
  ai_horde_api_key
)
optional_credentials=(
  gemini_api_key
  groq_api_key
  cerebras_api_key
  openrouter_api_key
  cloudflare_api_key
)
missing=0
for credential in "${required_credentials[@]}"; do
  if [ ! -s "$CREDENTIAL_ROOT/$credential" ]; then
    echo "missing credential: $CREDENTIAL_ROOT/$credential" >&2
    missing=1
  else
    chmod 0600 "$CREDENTIAL_ROOT/$credential"
    chown root:root "$CREDENTIAL_ROOT/$credential"
  fi
done
if [ "$missing" -ne 0 ]; then
  exit 1
fi
for credential in "${optional_credentials[@]}"; do
  if [ ! -e "$CREDENTIAL_ROOT/$credential" ]; then
    install -o root -g root -m 0600 /dev/null "$CREDENTIAL_ROOT/$credential"
  else
    chmod 0600 "$CREDENTIAL_ROOT/$credential"
    chown root:root "$CREDENTIAL_ROOT/$credential"
  fi
done

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is required on OCI before installation" >&2
  exit 1
fi
systemctl enable --now ollama.service
ollama pull nomic-embed-text

install -o root -g root -m 0644 "$APP_ROOT"/deploy/systemd/trevor-*.service /etc/systemd/system/
install -o root -g root -m 0644 "$APP_ROOT/deploy/systemd/trevor.target" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now trevor.target

if command -v tailscale >/dev/null 2>&1; then
  tailscale serve --bg --https=443 http://127.0.0.1:5001
fi

audit_deployment completed
trap - EXIT
systemctl --no-pager --full status trevor.target
