#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
UID_NUM="$(id -u)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/launchagents"
PID_DIR="$ROOT/logs/pids"

BACKEND_LABEL="com.user.perob-backend"
HTTPS_LABEL="com.user.perob-https"
SERVICE_PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
HTTPS_LISTEN_HOST="${PEROB_HTTPS_LISTEN_HOST:-127.0.0.1}"
TRUSTED_PYTHON="${PEROB_CREDENTIAL_PYTHON:-/usr/local/bin/python3}"
BACKEND_START_ATTEMPTS="${PEROB_BACKEND_START_ATTEMPTS:-30}"
CREDENTIAL_SOURCE_DIR="${TREVOR_CREDENTIAL_SOURCE_DIR:-$HOME/Library/Application Support/Trevor/credentials}"

BACKEND_PLIST="$HOME/Library/LaunchAgents/${BACKEND_LABEL}.plist"
HTTPS_PLIST="$HOME/Library/LaunchAgents/${HTTPS_LABEL}.plist"
BACKEND_PIDFILE="$PID_DIR/perob-backend-manual.pid"
HTTPS_PIDFILE="$PID_DIR/perob-https-manual.pid"

mkdir -p "$LOG_DIR" "$PID_DIR"

MANAGED_PYTHON=""
for candidate in "$ROOT"/.python-installations/cpython-3.12*/bin/python3.12; do
  if [[ -x "$candidate" ]]; then
    MANAGED_PYTHON="$candidate"
    break
  fi
done

PYTHON_BIN=""
for candidate in \
  "$ROOT/.venv312/bin/python3" \
  "$ROOT/.venv312/bin/python" \
  "$MANAGED_PYTHON" \
  "$ROOT/.venv311/bin/python3" \
  "$ROOT/.venv311/bin/python" \
  "$(command -v python3.12 || true)" \
  "$(command -v python3.11 || true)" \
  "$ROOT/.venv/bin/python3" \
  "$ROOT/.venv/bin/python" \
  "$(command -v python3 || true)"
do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PYTHON_BIN="$candidate"
    break
  fi
done

[[ -n "$PYTHON_BIN" ]] || { echo "[error] no runnable Python found" >&2; exit 1; }
if [[ ! -x "$TRUSTED_PYTHON" ]]; then
  TRUSTED_PYTHON="$PYTHON_BIN"
fi

PY_VERSION="$("$PYTHON_BIN" - <<'PY' 2>/dev/null || true
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
case "$PY_VERSION" in
  3.14|3.15|3.16|3.17|3.18|3.19)
    echo "[warn] Python ${PY_VERSION} may trigger Pydantic v1 compatibility warnings; prefer .venv312 or .venv311"
    ;;
esac

require_runtime_credentials() {
  local credential
  for credential in nvidia_api_key trevor_memory_key_b64; do
    if [[ ! -s "$CREDENTIAL_SOURCE_DIR/$credential" ]]; then
      echo "[error] missing private credential: $CREDENTIAL_SOURCE_DIR/$credential" >&2
      return 1
    fi
  done
}

load_agent() {
  local label="$1"
  local plist="$2"
  launchctl print "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || \
    launchctl bootstrap "gui/${UID_NUM}" "$plist" >/dev/null 2>&1 || true
  launchctl enable "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || true
}

unload_agent() {
  local label="$1"
  launchctl bootout "gui/${UID_NUM}/${label}" >/dev/null 2>&1 || true
}

stop_pidfile() {
  local pidfile="$1"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$pidfile"
  fi
}

stop_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "$pids" | xargs kill >/dev/null 2>&1 || true
  fi
}

start_manual_backend() {
  echo "[fallback] launchd cannot access the external-volume workspace; starting backend detached"
  "$PYTHON_BIN" "$ROOT/tools/launch_detached.py" \
    --cwd "$ROOT" \
    --pidfile "$BACKEND_PIDFILE" \
    --stdout "$LOG_DIR/perob-backend.out" \
    --stderr "$LOG_DIR/perob-backend.err" \
    --env OPENCLAW_ENABLED=true \
    --env PYTHONUNBUFFERED=1 \
    --env PYTHONUTF8=1 \
    --env "TREVOR_GEMINI_FREE_TIER_CONFIRMED=true" \
    --env "TREVOR_GROQ_FREE_TIER_CONFIRMED=true" \
    --env "TREVOR_WEB_SEARCH_ENABLED=true" \
    --env "TREVOR_DELIBERATION_ROLLOUT=shadow" \
    --env "TREVOR_DISABLE_KEYCHAIN=true" \
    --env "PATH=$SERVICE_PATH" \
    -- "$TRUSTED_PYTHON" -u "$ROOT/tools/launch_trevor_backend.py" \
      --python "$PYTHON_BIN" --credential-source "$CREDENTIAL_SOURCE_DIR" \
      -- -u "$ROOT/desktop_chat_app.py" web \
      --host 127.0.0.1 --port 5001 --energy-lite >/dev/null
}

start_manual_https() {
  echo "[fallback] starting HTTPS proxy detached"
  "$PYTHON_BIN" "$ROOT/tools/launch_detached.py" \
    --cwd "$ROOT" \
    --pidfile "$HTTPS_PIDFILE" \
    --stdout "$LOG_DIR/perob-https.out" \
    --stderr "$LOG_DIR/perob-https.err" \
    --env PYTHONUNBUFFERED=1 \
    --env PYTHONUTF8=1 \
    --env "PATH=$SERVICE_PATH" \
    -- "$PYTHON_BIN" -u "$ROOT/tools/https_local_proxy.py" \
      --listen-host "$HTTPS_LISTEN_HOST" \
      --listen-port 5443 \
      --upstream-host 127.0.0.1 \
      --upstream-port 5001 \
      --certfile "$ROOT/certs/local-https.crt" \
      --keyfile "$ROOT/certs/local-https.key" \
      --external-https-base https://perob.com:5443 >/dev/null
}

print_agent() {
  local label="$1"
  if launchctl print "gui/${UID_NUM}/${label}" >/tmp/"${label}".status 2>/dev/null; then
    echo "[ok] ${label}"
    rg -n "state =|pid =|last exit code =" /tmp/"${label}".status || true
  else
    echo "[info] ${label} not loaded"
  fi
}

status_ports() {
  echo "[ports]"
  lsof -nP -iTCP:5001 -sTCP:LISTEN || true
  lsof -nP -iTCP:5443 -sTCP:LISTEN || true
}

wait_http() {
  local url="$1"
  local name="$2"
  local attempts="${3:-30}"
  for _ in $(seq 1 "$attempts"); do
    if curl -kfsS -m 3 "$url" >/dev/null 2>&1; then
      echo "[ok] ${name}: ${url}"
      return 0
    fi
    sleep 1
  done
  echo "[warn] ${name} not ready: ${url}"
  return 1
}

wait_perob_https() {
  local attempts="${1:-30}"
  for _ in $(seq 1 "$attempts"); do
    if curl -kfsS -m 5 --resolve perob.com:5443:127.0.0.1 \
      https://perob.com:5443/status >/dev/null 2>&1; then
      echo "[ok] https proxy: https://perob.com:5443/status"
      return 0
    fi
    sleep 1
  done
  echo "[warn] https not ready: https://perob.com:5443/status"
  return 1
}

start_all() {
  require_runtime_credentials
  [[ -f "$BACKEND_PLIST" ]] || { echo "[error] missing: $BACKEND_PLIST"; exit 1; }
  [[ -f "$HTTPS_PLIST" ]] || { echo "[error] missing: $HTTPS_PLIST"; exit 1; }

  if [[ "$ROOT" == /Volumes/* && "${PEROB_USE_LAUNCHAGENT:-0}" != "1" ]]; then
    echo "[info] external-volume workspace detected; using Terminal-safe background mode"
    start_manual_backend
    wait_http "http://127.0.0.1:5001/health/live" "backend fallback live"
  else
    load_agent "$BACKEND_LABEL" "$BACKEND_PLIST"
    if ! wait_http "http://127.0.0.1:5001/health/live" "backend live" "$BACKEND_START_ATTEMPTS"; then
      unload_agent "$BACKEND_LABEL"
      stop_port 5001
      start_manual_backend
      wait_http "http://127.0.0.1:5001/health/live" "backend fallback live"
    fi
  fi

  if [[ "$ROOT" == /Volumes/* && "${PEROB_USE_LAUNCHAGENT:-0}" != "1" ]]; then
    start_manual_https
    wait_perob_https 12 || true
  else
    load_agent "$HTTPS_LABEL" "$HTTPS_PLIST"
    if ! wait_perob_https 6; then
      unload_agent "$HTTPS_LABEL"
      stop_port 5443
      start_manual_https
    fi
  fi

  wait_http "http://127.0.0.1:5001/health/ready" "backend + frontend" || true
  curl -kfsS -m 5 --resolve perob.com:5443:127.0.0.1 \
    https://perob.com:5443/status >/dev/null 2>&1 \
    && echo "[ok] https: https://perob.com:5443" \
    || echo "[warn] https not ready: https://perob.com:5443"
}

stop_all() {
  unload_agent "$HTTPS_LABEL"
  unload_agent "$BACKEND_LABEL"
  stop_pidfile "$HTTPS_PIDFILE"
  stop_pidfile "$BACKEND_PIDFILE"
  stop_port 5443
  stop_port 5001
}

status_all() {
  print_agent "$BACKEND_LABEL"
  print_agent "$HTTPS_LABEL"
  status_ports
}

case "$ACTION" in
  start)
    start_all
    status_all
    ;;
  stop)
    stop_all
    status_all
    ;;
  restart)
    stop_all
    sleep 1
    start_all
    status_all
    ;;
  status)
    status_all
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 1
    ;;
esac
