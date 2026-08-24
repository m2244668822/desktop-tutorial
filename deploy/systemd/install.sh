#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/bin:$PATH"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi

SOURCE_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
APP_ROOT="/opt/trevor/app"
RELEASE_ROOT="/opt/trevor/releases"
PYTHON_ROOT="/opt/trevor/python"
DATA_ROOT="/var/lib/trevor"
CONFIG_ROOT="/etc/trevor"
CREDENTIAL_ROOT="$CONFIG_ROOT/credentials"
UV_CACHE_ROOT="$DATA_ROOT/cache/uv"
FALKORDB_MODULE_CACHE_ROOT="$DATA_ROOT/cache/falkordb"
FALKORDB_MODULE_VERSION="v4.18.3"
FALKORDB_RHEL9_MODULE_SHA256="0f8f7ba39a5f5c9bd1a2e270915bb1435369d9413773a91de6bcc84c5b0f2ea7"
DEPLOY_ID="$(date +%Y%m%d-%H%M%S)-$$"
BUILD_ROOT="$RELEASE_ROOT/.staging-$DEPLOY_ID"
PREVIOUS_APP_ROOT="$RELEASE_ROOT/previous-$DEPLOY_ID"
FAILED_APP_ROOT="$RELEASE_ROOT/failed-$DEPLOY_ID"
UNIT_BACKUP_ROOT="$RELEASE_ROOT/.units-$DEPLOY_ID"
TREVOR_SERVICES=(
  trevor-api.service
  trevor-graphiti.service
  trevor-autonomy.service
  trevor-worker.service
)
TREVOR_UNITS=(
  trevor-api.service
  trevor-graphiti.service
  trevor-autonomy.service
  trevor-worker.service
  trevor.target
)
CUTOVER_STARTED=0
PREVIOUS_APP_SAVED=0
NEW_APP_ACTIVATED=0
ACTIVE_SERVICES=()
READINESS_ATTEMPTS=180
READINESS_STABLE_PROBES=5

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
    && command -v rsync >/dev/null 2>&1 \
    && [ -x /usr/bin/python3 ]; then
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates curl gcc gcc-c++ git make python3 rsync
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      build-essential ca-certificates curl git python3 rsync
  else
    echo "supported package manager not found; install C/C++, curl, git, make, Python 3, and rsync" >&2
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
  local app_root="$1"
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

  graphiti_python="$app_root/services/graphiti_sidecar/.venv/bin/python"
  module_path="$(
    cd "$app_root/services/graphiti_sidecar"
    runuser -u trevor -- "$graphiti_python" -c \
      'from pathlib import Path; import redislite; print(Path(redislite.__file__).resolve().parent / "bin" / "falkordb.so")'
  )"
  install -o trevor -g trevor -m 0755 "$cache_path" "$module_path"
}

audit_deployment() {
  local status="$1"
  local audit_root=""
  if [ -x "$BUILD_ROOT/.venv/bin/python" ]; then
    audit_root="$BUILD_ROOT"
  elif [ -x "$APP_ROOT/.venv/bin/python" ]; then
    audit_root="$APP_ROOT"
  else
    return 1
  fi
  (
    cd "$audit_root"
    runuser -u trevor -- env TREVOR_DATA_DIR="$DATA_ROOT" \
      "$audit_root/.venv/bin/python" tools/trevor_operations.py audit \
      --event deployment \
      --status "$status" \
      --subject oci-systemd \
      --data-root "$DATA_ROOT"
  )
}

cleanup_staging_artifacts() {
  case "$BUILD_ROOT" in
    "$RELEASE_ROOT"/.staging-*) ;;
    *) return 1 ;;
  esac
  case "$UNIT_BACKUP_ROOT" in
    "$RELEASE_ROOT"/.units-*) ;;
    *) return 1 ;;
  esac
  rm -rf -- "$BUILD_ROOT" "$UNIT_BACKUP_ROOT"
}

migrate_legacy_service_data() {
  /usr/bin/python3 - "$DATA_ROOT" trevor <<'PY_MIGRATE_TREVOR_DATA'
import os
import pwd
import stat
import sys


data_root = os.path.abspath(sys.argv[1])
account = pwd.getpwnam(sys.argv[2])
target_uid = account.pw_uid
target_gid = account.pw_gid
directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def require_expected_owner(metadata):
    if metadata.st_uid not in (0, target_uid):
        raise RuntimeError("unexpected_service_data_owner")


def open_directory(parent_fd, name, create=False):
    try:
        descriptor = os.open(name, directory_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        descriptor = os.open(name, directory_flags, dir_fd=parent_fd)
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise RuntimeError("service_data_directory_required")
    require_expected_owner(metadata)
    os.fchown(descriptor, target_uid, target_gid)
    os.fchmod(descriptor, 0o700)
    return descriptor


def migrate_regular_file(parent_fd, name):
    try:
        descriptor = os.open(name, file_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("service_data_regular_file_required")
        if metadata.st_nlink != 1:
            raise RuntimeError("service_data_hardlink_rejected")
        require_expected_owner(metadata)
        os.fchown(descriptor, target_uid, target_gid)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


parent_path, root_name = os.path.split(data_root.rstrip(os.sep))
if not parent_path or not root_name:
    raise RuntimeError("invalid_service_data_root")
parent_fd = os.open(parent_path, directory_flags)
try:
    root_fd = open_directory(parent_fd, root_name, create=True)
finally:
    os.close(parent_fd)
try:
    for directory_name, file_name in (
        ("auth", "api_keys.json"),
        ("audit", "events.jsonl"),
    ):
        directory_fd = open_directory(root_fd, directory_name, create=True)
        try:
            migrate_regular_file(directory_fd, file_name)
        finally:
            os.close(directory_fd)
finally:
    os.close(root_fd)
PY_MIGRATE_TREVOR_DATA
}

json_health_ready() {
  local url="$1"
  local required_field="${2:--}"
  curl --fail --silent --show-error --max-time 5 "$url" \
    | runuser -u trevor -- "$APP_ROOT/.venv/bin/python" -c '
import json
import sys

payload = json.load(sys.stdin)
required_field = sys.argv[1]
ready = isinstance(payload, dict) and payload.get("ok") is True
if required_field != "-":
    ready = ready and payload.get(required_field) is True
raise SystemExit(0 if ready else 1)
' "$required_field" 2>/dev/null
}

wait_for_service_readiness() {
  local attempt service stable_probes=0
  for ((attempt = 1; attempt <= READINESS_ATTEMPTS; attempt += 1)); do
    for service in "${TREVOR_SERVICES[@]}"; do
      if ! systemctl is-active --quiet "$service"; then
        echo "Trevor service stopped during readiness: $service" >&2
        return 1
      fi
    done
    if json_health_ready \
      http://127.0.0.1:5001/health/ready required_ready \
      && json_health_ready http://127.0.0.1:8091/health; then
      stable_probes=$((stable_probes + 1))
      if [ "$stable_probes" -ge "$READINESS_STABLE_PROBES" ]; then
        return 0
      fi
    else
      stable_probes=0
    fi
    sleep 2
  done
  echo "Trevor services did not reach stable readiness" >&2
  return 1
}

rollback_cutover() {
  local service unit
  if [ "$CUTOVER_STARTED" -ne 1 ]; then
    return
  fi
  systemctl stop "${TREVOR_SERVICES[@]}" 2>/dev/null || true
  if [ "$NEW_APP_ACTIVATED" -eq 1 ] && [ -e "$APP_ROOT" ]; then
    mv "$APP_ROOT" "$FAILED_APP_ROOT" || true
  fi
  if [ "$PREVIOUS_APP_SAVED" -eq 1 ]; then
    if [ -e "$PREVIOUS_APP_ROOT" ]; then
      mv "$PREVIOUS_APP_ROOT" "$APP_ROOT"
    fi
  fi
  for unit in "${TREVOR_UNITS[@]}"; do
    if [ -f "$UNIT_BACKUP_ROOT/$unit" ]; then
      install -o root -g root -m 0644 \
        "$UNIT_BACKUP_ROOT/$unit" "/etc/systemd/system/$unit"
    else
      rm -f "/etc/systemd/system/$unit"
    fi
  done
  systemctl daemon-reload || true
  for service in "${ACTIVE_SERVICES[@]}"; do
    systemctl start "$service" || true
  done
}

deployment_exit() {
  local exit_code=$?
  trap - EXIT
  if [ "$exit_code" -ne 0 ]; then
    rollback_cutover || true
    audit_deployment failed >/dev/null 2>&1 || true
    cleanup_staging_artifacts || true
  fi
  exit "$exit_code"
}

ensure_host_tools
ensure_uv

if ! id trevor >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/trevor --shell /usr/sbin/nologin trevor
fi

install -d -o trevor -g trevor -m 0700 \
  "$DATA_ROOT" "$UV_CACHE_ROOT" "$FALKORDB_MODULE_CACHE_ROOT"
migrate_legacy_service_data
trap deployment_exit EXIT
install -d -o root -g root -m 0755 \
  /opt/trevor "$RELEASE_ROOT" "$CONFIG_ROOT"
install -d -o trevor -g trevor -m 0755 "$PYTHON_ROOT" "$BUILD_ROOT"
install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT" "$UNIT_BACKUP_ROOT"

rsync -a \
  --exclude '.git/' \
  --exclude '.venv*' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude '.env*' \
  "$SOURCE_ROOT/" "$BUILD_ROOT/"
chown -R trevor:trevor "$BUILD_ROOT"
cd "$BUILD_ROOT"

runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  uv python install 3.12
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  uv venv --python 3.12 --clear "$BUILD_ROOT/.venv"
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  uv pip install --python "$BUILD_ROOT/.venv/bin/python" \
  --requirements "$BUILD_ROOT/requirements.txt"
audit_deployment started >/dev/null
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  uv venv --python 3.12 --clear "$BUILD_ROOT/services/graphiti_sidecar/.venv"
runuser -u trevor -- env \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT" \
  UV_PROJECT_ENVIRONMENT="$BUILD_ROOT/services/graphiti_sidecar/.venv" \
  uv sync --project "$BUILD_ROOT/services/graphiti_sidecar" --frozen --no-dev
install_falkordb_platform_module "$BUILD_ROOT"
if command -v restorecon >/dev/null 2>&1; then
  restorecon -RF "$PYTHON_ROOT" "$BUILD_ROOT"
fi

if [ ! -f "$CONFIG_ROOT/trevor.env" ]; then
  install -o root -g root -m 0600 \
    "$BUILD_ROOT/deploy/systemd/trevor.env.example" "$CONFIG_ROOT/trevor.env"
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

for unit in "${TREVOR_UNITS[@]}"; do
  if [ -f "/etc/systemd/system/$unit" ]; then
    cp -a "/etc/systemd/system/$unit" "$UNIT_BACKUP_ROOT/$unit"
  fi
done
for service in "${TREVOR_SERVICES[@]}"; do
  if systemctl is-active --quiet "$service"; then
    ACTIVE_SERVICES+=("$service")
  fi
done

CUTOVER_STARTED=1
systemctl stop "${TREVOR_SERVICES[@]}" 2>/dev/null || true
for service in "${TREVOR_SERVICES[@]}"; do
  if systemctl is-active --quiet "$service"; then
    echo "Trevor service could not be stopped safely: $service" >&2
    exit 1
  fi
done
migrate_legacy_service_data
if [ -e "$APP_ROOT" ]; then
  mv "$APP_ROOT" "$PREVIOUS_APP_ROOT"
  PREVIOUS_APP_SAVED=1
fi
mv "$BUILD_ROOT" "$APP_ROOT"
NEW_APP_ACTIVATED=1
if command -v restorecon >/dev/null 2>&1; then
  restorecon -RF "$APP_ROOT"
fi

install -o root -g root -m 0644 "$APP_ROOT"/deploy/systemd/trevor-*.service /etc/systemd/system/
install -o root -g root -m 0644 "$APP_ROOT/deploy/systemd/trevor.target" /etc/systemd/system/
systemctl daemon-reload
systemctl enable trevor.target
systemctl restart trevor-graphiti.service
systemctl restart trevor-api.service
systemctl restart trevor-autonomy.service trevor-worker.service
systemctl start trevor.target
wait_for_service_readiness

if command -v tailscale >/dev/null 2>&1 \
  && tailscale status >/dev/null 2>&1; then
  tailscale serve --bg --https=443 http://127.0.0.1:5001
fi

systemctl --no-pager --full status trevor.target
audit_deployment completed
CUTOVER_STARTED=0
cleanup_staging_artifacts
trap - EXIT
