#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

AUTONOMY_DIR="${ROOT_DIR}/data_hdd_storage/autonomy"
LOG_DIR="${ROOT_DIR}/logs"
PID_FILE="${LOG_DIR}/autopilot_daemon.pid"
OUT_LOG="${LOG_DIR}/autopilot_daemon.out.log"
ERR_LOG="${LOG_DIR}/autopilot_daemon.err.log"
STATE_FILE="${AUTONOMY_DIR}/daemon_state.json"
QUEUE_FILE="${AUTONOMY_DIR}/task_queue.json"

INTERVAL="${AUTOPILOT_INTERVAL:-30}"
SKILL_CHECK_MINUTES="${AUTOPILOT_SKILL_CHECK_MINUTES:-10}"
SKIP_HEALTH="${AUTOPILOT_SKIP_HEALTH:-1}"

mkdir -p "$LOG_DIR" "$AUTONOMY_DIR"

is_running() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  ps -p "$pid" >/dev/null 2>&1
}

start_daemon() {
  if is_running; then
    echo "[autopilot] already running pid=$(cat "$PID_FILE")"
    return 0
  fi
  local cmd=(
    "$PYTHON_BIN" "$ROOT_DIR/system_main.py" autopilot
    --autopilot-interval "$INTERVAL"
    --autopilot-skill-check-minutes "$SKILL_CHECK_MINUTES"
  )
  if [[ "$SKIP_HEALTH" == "1" ]]; then
    cmd+=(--skip-health)
  fi
  nohup "${cmd[@]}" >"$OUT_LOG" 2>"$ERR_LOG" &
  echo $! >"$PID_FILE"
  sleep 1
  if is_running; then
    echo "[autopilot] started pid=$(cat "$PID_FILE") interval=${INTERVAL}s skill_check=${SKILL_CHECK_MINUTES}min"
    return 0
  fi
  echo "[autopilot] failed to start, check logs: $OUT_LOG / $ERR_LOG" >&2
  return 1
}

stop_daemon() {
  if ! is_running; then
    echo "[autopilot] not running"
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" >/dev/null 2>&1 || true
  sleep 1
  if ps -p "$pid" >/dev/null 2>&1; then
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$PID_FILE"
  echo "[autopilot] stopped"
}

status_daemon() {
  if is_running; then
    echo "[autopilot] running pid=$(cat "$PID_FILE")"
  else
    echo "[autopilot] not running"
  fi
  if [[ -f "$STATE_FILE" ]]; then
    echo "--- state ---"
    sed -n '1,120p' "$STATE_FILE"
  fi
  if [[ -f "$QUEUE_FILE" ]]; then
    echo "--- queue ---"
    sed -n '1,120p' "$QUEUE_FILE"
  fi
}

case "$ACTION" in
start)
  start_daemon
  ;;
stop)
  stop_daemon
  ;;
restart)
  stop_daemon
  start_daemon
  ;;
status)
  status_daemon
  ;;
*)
  echo "usage: $0 {start|stop|restart|status}" >&2
  exit 1
  ;;
esac
