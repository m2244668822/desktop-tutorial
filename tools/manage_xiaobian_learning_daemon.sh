#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOOP_SCRIPT="${ROOT_DIR}/tools/run_xiaobian_continuous_learning.py"
LOG_DIR="${ROOT_DIR}/.sync_user_project/logs"
PID_FILE="${LOG_DIR}/xiaobian_learning_daemon.pid"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
LAUNCH_LABEL="com.chengcheng.xiaobian.learning"
PLIST_PATH="$HOME/Library/LaunchAgents/${LAUNCH_LABEL}.plist"
UID_NUM="$(id -u)"
SERVER_URL="${XIAOBIAN_SERVER_URL:-http://127.0.0.1:5001}"
INTERVAL="${XIAOBIAN_LEARNING_INTERVAL:-900}"
LOG_FILE="${LOG_DIR}/xiaobian_continuous_learning.log"

if [[ ! -f "$LOOP_SCRIPT" ]]; then
  echo "[error] loop script not found: $LOOP_SCRIPT" >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

is_loop_running() {
  ps aux | rg -F "${LOOP_SCRIPT}" | rg -v "rg " >/dev/null 2>&1
}

start_fallback_background() {
  nohup /bin/bash -lc "cd '${ROOT_DIR}' && exec '${PYTHON_BIN}' -u '${LOOP_SCRIPT}' --server-url '${SERVER_URL}' --interval '${INTERVAL}'" \
    >> "${LOG_FILE}" \
    2>&1 < /dev/null &
  echo $! > "${PID_FILE}"
  echo "[ok] fallback background started, pid=$(cat "${PID_FILE}")"
}

write_plist() {
  cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LAUNCH_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd '${ROOT_DIR}' &amp;&amp; export PYTHONUNBUFFERED=1 ; exec '${PYTHON_BIN}' -u '${LOOP_SCRIPT}' --server-url '${SERVER_URL}' --interval '${INTERVAL}'</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>${LOG_FILE}</string>

  <key>StandardErrorPath</key>
  <string>${LOG_FILE}</string>
</dict>
</plist>
PLIST
}

start_daemon() {
  write_plist
  launchctl bootout "gui/${UID_NUM}" "$PLIST_PATH" >/dev/null 2>&1 || true
  if ! launchctl bootstrap "gui/${UID_NUM}" "$PLIST_PATH"; then
    echo "[warn] launchctl bootstrap failed, fallback to background mode"
    start_fallback_background
    return
  fi
  launchctl enable "gui/${UID_NUM}/${LAUNCH_LABEL}" >/dev/null 2>&1 || true
  sleep 1
  if ! is_loop_running; then
    echo "[warn] launchd job loaded but loop is not running, fallback to background mode"
    start_fallback_background
    return
  fi
  echo "[ok] daemon started: ${LAUNCH_LABEL}"
  echo "[info] server=${SERVER_URL} interval=${INTERVAL}s"
}

stop_daemon() {
  launchctl bootout "gui/${UID_NUM}" "$PLIST_PATH" >/dev/null 2>&1 || true
  pkill -f "${LOOP_SCRIPT}" >/dev/null 2>&1 || true
  if [[ -f "${PID_FILE}" ]]; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
    fi
    rm -f "${PID_FILE}" >/dev/null 2>&1 || true
  fi
  echo "[ok] daemon stopped: ${LAUNCH_LABEL}"
}

status_daemon() {
  if launchctl print "gui/${UID_NUM}/${LAUNCH_LABEL}" >/tmp/${LAUNCH_LABEL}.status 2>/dev/null; then
    echo "[ok] daemon is loaded: ${LAUNCH_LABEL}"
    rg -n "state =|pid =|last exit code =" /tmp/${LAUNCH_LABEL}.status || true
  else
    echo "[info] daemon is not loaded: ${LAUNCH_LABEL}"
  fi

  if [[ -f "${PID_FILE}" ]]; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      echo "[ok] fallback process running: pid=${pid}"
    fi
  fi

  echo "[info] log: ${LOG_FILE}"
}

tail_logs() {
  touch "${LOG_FILE}"
  tail -n 120 -f "${LOG_FILE}"
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
  tail)
    tail_logs
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|tail}" >&2
    exit 1
    ;;
esac
