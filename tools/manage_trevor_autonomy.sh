#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="${TREVOR_DATA_DIR:-$HOME/Library/Application Support/Trevor}"
CREDENTIAL_ROOT="${TREVOR_CREDENTIAL_SOURCE_DIR:-$HOME/Library/Application Support/Trevor/credentials}"
LOG_ROOT="$HOME/Library/Logs/Trevor"
PID_FILE="$DATA_ROOT/run/autonomy-manual.pid"
STDOUT_FILE="$LOG_ROOT/autonomy.log"
STDERR_FILE="$LOG_ROOT/autonomy.error.log"
LABEL="com.trevor.autonomy"

PYTHON_BIN=""
for candidate in \
  "$ROOT/.venv312/bin/python3" \
  "$ROOT/.venv312/bin/python" \
  "$(command -v python3.12 || true)" \
  "$(command -v python3.11 || true)" \
  "$(command -v python3 || true)"
do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PYTHON_BIN="$candidate"
    break
  fi
done
[[ -n "$PYTHON_BIN" ]] || { echo "[error] Python runtime not found" >&2; exit 1; }

for credential in nvidia_api_key trevor_memory_key_b64; do
  [[ -s "$CREDENTIAL_ROOT/$credential" ]] || {
    echo "[error] missing private credential: $CREDENTIAL_ROOT/$credential" >&2
    exit 1
  }
done

mkdir -p "$DATA_ROOT/run" "$LOG_ROOT"
chmod 700 "$DATA_ROOT" "$DATA_ROOT/run" "$LOG_ROOT" 2>/dev/null || true

current_pid() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  printf '%s\n' "$pid"
}

stop_service() {
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
  local pid
  pid="$(current_pid || true)"
  if [[ -n "$pid" ]]; then
    kill "$pid" >/dev/null 2>&1 || true
    for _attempt in $(seq 1 20); do
      kill -0 "$pid" >/dev/null 2>&1 || break
      sleep 0.1
    done
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$PID_FILE"
}

start_service() {
  local pid
  pid="$(current_pid || true)"
  if [[ -n "$pid" ]]; then
    echo "[ok] autonomy already running pid=$pid"
    return 0
  fi
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
  "$PYTHON_BIN" "$ROOT/tools/launch_detached.py" \
    --cwd "$ROOT" \
    --pidfile "$PID_FILE" \
    --stdout "$STDOUT_FILE" \
    --stderr "$STDERR_FILE" \
    --env "TREVOR_DATA_DIR=$DATA_ROOT" \
    --env "CREDENTIALS_DIRECTORY=$CREDENTIAL_ROOT" \
    --env "TREVOR_DEPLOYMENT=mac" \
    --env "TREVOR_MEMORY_ENCRYPTION=required" \
    --env "TREVOR_DISABLE_KEYCHAIN=true" \
    --env "PYTHONUNBUFFERED=1" \
    -- "$PYTHON_BIN" -u "$ROOT/tools/agent_autonomy_daemon.py" --heartbeat 60 --evaluation 900 --nightly-hour 3 >/dev/null
  sleep 2
  pid="$(current_pid || true)"
  [[ -n "$pid" ]] || { echo "[error] autonomy failed to start" >&2; exit 1; }
  echo "[ok] autonomy running pid=$pid"
}

status_service() {
  local pid
  pid="$(current_pid || true)"
  if [[ -n "$pid" ]]; then
    echo "[ok] autonomy running pid=$pid"
    return 0
  fi
  echo "[info] autonomy stopped"
  return 1
}

case "$ACTION" in
  start) start_service ;;
  stop) stop_service; status_service || true ;;
  restart) stop_service; start_service ;;
  status) status_service ;;
  *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
