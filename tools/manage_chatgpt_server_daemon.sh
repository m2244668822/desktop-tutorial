#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${ROOT_DIR}/.sync_user_project"
SERVER_SCRIPT="$PROJECT_DIR/chatgpt_server.py"
ENV_FILE="$PROJECT_DIR/.env"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/chatgpt_server.pid"
LAUNCH_LOG_DIR="${LAUNCH_LOG_DIR:-$HOME/.chat_frontend}"
LAUNCH_STDOUT_PATH="$LAUNCH_LOG_DIR/chatgpt_server_launchd.out"
LAUNCH_STDERR_PATH="$LAUNCH_LOG_DIR/chatgpt_server_launchd.err"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
if [[ -z "${PYTHON_BIN}" || ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -x "${PROJECT_DIR}/../.venv/bin/python3" ]]; then
  PYTHON_BIN="${PROJECT_DIR}/../.venv/bin/python3"
fi
LAUNCH_LABEL="com.chengcheng.chatgpt.server"
PLIST_PATH="$HOME/Library/LaunchAgents/${LAUNCH_LABEL}.plist"
UID_NUM="$(id -u)"
SERVER_PORT="${CHAT_SERVER_PORT:-5001}"
SERVER_HOST="${CHAT_SERVER_HOST:-127.0.0.1}"

if [[ ! -f "$SERVER_SCRIPT" ]]; then
  echo "[error] server script not found: $SERVER_SCRIPT" >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$LAUNCH_LOG_DIR" "$HOME/Library/LaunchAgents"

is_listening() {
  lsof -nP -iTCP:"${SERVER_PORT}" -sTCP:LISTEN >/dev/null 2>&1
}

start_fallback_background() {
  nohup /bin/bash -lc "cd '${PROJECT_DIR}' && export CHAT_SERVER_HOST='${SERVER_HOST}' ; exec '${PYTHON_BIN}' '${SERVER_SCRIPT}'" \
    > "${LOG_DIR}/chatgpt_server.stdout.log" \
    2> "${LOG_DIR}/chatgpt_server.stderr.log" < /dev/null &
  echo $! > "${PID_FILE}"
  echo "[ok] fallback background started (nohup), pid=$(cat "${PID_FILE}")"
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
    <string>cd '${PROJECT_DIR}' &amp;&amp; export PYTHONUNBUFFERED=1 ; export CHAT_SERVER_HOST='${SERVER_HOST}' ; exec '${PYTHON_BIN}' '${SERVER_SCRIPT}'</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${PROJECT_DIR}</string>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>${LAUNCH_STDOUT_PATH}</string>

  <key>StandardErrorPath</key>
  <string>${LAUNCH_STDERR_PATH}</string>
</dict>
</plist>
PLIST
}

start_daemon() {
  write_plist
  launchctl bootout "gui/${UID_NUM}" "$PLIST_PATH" >/dev/null 2>&1 || true
  if ! launchctl bootstrap "gui/${UID_NUM}" "$PLIST_PATH"; then
    echo "[warn] launchctl bootstrap failed, using fallback background mode"
    start_fallback_background
    return
  fi
  launchctl enable "gui/${UID_NUM}/${LAUNCH_LABEL}" >/dev/null 2>&1 || true
  # RunAtLoad=true already starts the job; avoid kickstart blocking in non-GUI shells.
  sleep 1
  if ! is_listening; then
    echo "[warn] launchd loaded but port ${SERVER_PORT} not listening, using fallback background mode"
    start_fallback_background
  fi
  echo "[ok] daemon started: ${LAUNCH_LABEL} (or fallback)"
  echo "[info] plist: ${PLIST_PATH}"
}

stop_daemon() {
  launchctl bootout "gui/${UID_NUM}" "$PLIST_PATH" >/dev/null 2>&1 || true
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
    else
      echo "[info] fallback pid file exists but process not running"
    fi
  fi

  if is_listening; then
    echo "[ok] port ${SERVER_PORT} is listening"
  else
    echo "[info] port ${SERVER_PORT} is not listening"
  fi
}

tail_logs() {
  touch "$LOG_DIR/chatgpt_server.stdout.log" "$LOG_DIR/chatgpt_server.stderr.log"
  tail -n 120 -f "$LOG_DIR/chatgpt_server.stdout.log" "$LOG_DIR/chatgpt_server.stderr.log"
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
