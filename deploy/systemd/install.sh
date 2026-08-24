#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/bin:$PATH"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi

SOURCE_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
APP_ROOT="/opt/trevor/app"
PYTHON_ROOT="/opt/trevor/python"
DATA_ROOT="/var/lib/trevor"
CONFIG_ROOT="/etc/trevor"
CREDENTIAL_ROOT="$CONFIG_ROOT/credentials"
UV_CACHE_ROOT="$DATA_ROOT/cache/uv"
FALKORDB_MODULE_CACHE_ROOT="$DATA_ROOT/cache/falkordb"
FALKORDB_MODULE_VERSION="v4.18.3"
FALKORDB_RHEL9_MODULE_SHA256="0f8f7ba39a5f5c9bd1a2e270915bb1435369d9413773a91de6bcc84c5b0f2ea7"

if [ ! -f "$SOURCE_ROOT/system_main.py" ]; then
  echo "invalid Trevor source root" >&2
  exit 1
fi

ensure_host_tools() {
  if command -v curl >/dev/null 2>&1 \
    && command -v gcc >/dev/null 2>&1 \
    && command -v g++ >/dev/null 2>&1 \
    && command -v git >/dev/null 2>&1 \
    && command -v make >/dev/null 2>&1 \
    && command -v rsync >/dev/null 2>&1; then
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates curl gcc gcc-c++ git make rsync
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      build-essential ca-certificates curl git rsync
  else
    echo "supported package manager not found; install C/C++, curl, git, make, and rsync" >&2
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

install_falkordb_platform_module() {
  local os_id os_major asset cache_path temporary module_path graphiti_python
  os_id="$(. /etc/os-release; printf '%s' "$ID")"
  os_major="$(. /etc/os-release; printf '%s' "${VERSION_ID%%.*}")"
  if [ "$(uname -m)" != "x86_64" ]; then
    return
  fi
  case "$os_id:$os_major" in
    ol:9|rhel:9|rocky:9|almalinux:9)
      asset="falkordb-rhel9-x64.so"
      ;;
    *)
      return
      ;;
  esac

  install -d -o trevor -g trevor -m 0700 "$FALKORDB_MODULE_CACHE_ROOT"
  cache_path="$FALKORDB_MODULE_CACHE_ROOT/$asset"
  if ! printf '%s  %s\n' "$FALKORDB_RHEL9_MODULE_SHA256" "$cache_path" \
    | sha256sum --check --status 2>/dev/null; then
    temporary="$(mktemp)"
    if ! curl --proto '=https' --tlsv1.2 -fL --retry 3 --retry-delay 2 \
      -o "$temporary" \
      "https://github.com/FalkorDB/FalkorDB/releases/download/$FALKORDB_MODULE_VERSION/$asset"; then
      rm -f "$temporary"
      return 1
    fi
    printf '%s  %s\n' "$FALKORDB_RHEL9_MODULE_SHA256" "$temporary" \
      | sha256sum --check --status
    install -o trevor -g trevor -m 0755 "$temporary" "$cache_path"
    rm -f "$temporary"
  fi
  if ldd "$cache_path" 2>&1 | grep -q 'not found'; then
    echo "FalkorDB platform module is incompatible with this OCI host" >&2
    return 1
  fi

  graphiti_python="$APP_ROOT/services/graphiti_sidecar/.venv/bin/python"
  module_path="$(
    cd "$APP_ROOT/services/graphiti_sidecar"
    runuser -u trevor -- "$graphiti_python" -c \
      'from pathlib import Path; import redislite; print(Path(redislite.__file__).resolve().parent / "bin" / "falkordb.so")'
  )"
  install -o trevor -g trevor -m 0755 "$cache_path" "$module_path"
}

ensure_host_tools
ensure_uv

if ! id trevor >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/trevor --shell /usr/sbin/nologin trevor
fi

install -d -o trevor -g trevor -m 0700 \
  "$DATA_ROOT" "$UV_CACHE_ROOT" "$FALKORDB_MODULE_CACHE_ROOT"
install -d -o root -g root -m 0755 /opt/trevor "$APP_ROOT" "$CONFIG_ROOT"
install -d -o trevor -g trevor -m 0755 "$PYTHON_ROOT"
install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT"

if [ "$(realpath "$SOURCE_ROOT")" != "$(realpath "$APP_ROOT")" ]; then
  rsync -a --exclude '.venv*' --exclude 'data/' --exclude 'logs/' --exclude '.env*' \
    "$SOURCE_ROOT/" "$APP_ROOT/"
fi
chown -R trevor:trevor "$APP_ROOT"
cd "$APP_ROOT"

runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  uv python install 3.12
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  uv venv --python 3.12 --clear "$APP_ROOT/.venv"
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  uv pip install --python "$APP_ROOT/.venv/bin/python" \
  --requirements "$APP_ROOT/requirements.txt"
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  uv venv --python 3.12 --clear "$APP_ROOT/services/graphiti_sidecar/.venv"
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  UV_PROJECT_ENVIRONMENT="$APP_ROOT/services/graphiti_sidecar/.venv" \
  uv sync --project "$APP_ROOT/services/graphiti_sidecar" --frozen --no-dev
install_falkordb_platform_module
if command -v restorecon >/dev/null 2>&1; then
  restorecon -RF "$PYTHON_ROOT" "$APP_ROOT"
fi

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

if command -v tailscale >/dev/null 2>&1 \
  && tailscale status >/dev/null 2>&1; then
  tailscale serve --bg --https=443 http://127.0.0.1:5001
fi

audit_deployment completed
trap - EXIT
systemctl --no-pager --full status trevor.target
