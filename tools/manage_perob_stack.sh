#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
UID_NUM="$(id -u)"

BACKEND_LABEL="com.user.perob-backend"
HTTPS_LABEL="com.user.perob-https"
FRONTEND_LABEL="com.user.desktop-chat-frontend"

BACKEND_PLIST="$HOME/Library/LaunchAgents/${BACKEND_LABEL}.plist"
HTTPS_PLIST="$HOME/Library/LaunchAgents/${HTTPS_LABEL}.plist"
FRONTEND_PLIST="$HOME/Library/LaunchAgents/${FRONTEND_LABEL}.plist"

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
  lsof -nP -iTCP:5002 -sTCP:LISTEN || true
  lsof -nP -iTCP:5443 -sTCP:LISTEN || true
}

wait_http() {
  local url="$1"
  local name="$2"
  for _ in $(seq 1 30); do
    if curl -fsS -m 3 "$url" >/dev/null 2>&1; then
      echo "[ok] ${name}: ${url}"
      return 0
    fi
    sleep 1
  done
  echo "[warn] ${name} not ready: ${url}"
  return 1
}

start_all() {
  [[ -f "$BACKEND_PLIST" ]] || { echo "[error] missing: $BACKEND_PLIST"; exit 1; }
  [[ -f "$HTTPS_PLIST" ]] || { echo "[error] missing: $HTTPS_PLIST"; exit 1; }
  [[ -f "$FRONTEND_PLIST" ]] || { echo "[error] missing: $FRONTEND_PLIST"; exit 1; }

  load_agent "$BACKEND_LABEL" "$BACKEND_PLIST"
  load_agent "$HTTPS_LABEL" "$HTTPS_PLIST"
  load_agent "$FRONTEND_LABEL" "$FRONTEND_PLIST"

  wait_http "http://127.0.0.1:5001/status" "backend" || true
  wait_http "http://127.0.0.1:5002/health" "frontend" || true
  curl -kfsS -m 5 https://127.0.0.1:5443/status >/dev/null 2>&1 \
    && echo "[ok] https: https://perob.com:5443" \
    || echo "[warn] https not ready: https://perob.com:5443"
}

stop_all() {
  unload_agent "$FRONTEND_LABEL"
  unload_agent "$HTTPS_LABEL"
  unload_agent "$BACKEND_LABEL"
}

status_all() {
  print_agent "$BACKEND_LABEL"
  print_agent "$HTTPS_LABEL"
  print_agent "$FRONTEND_LABEL"
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
