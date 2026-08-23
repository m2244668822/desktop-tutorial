#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="/Users/user/.chat_frontend"
PROJECT_DIR="$ROOT_DIR/.sync_user_project"
FULL_BACKEND_SCRIPT="$PROJECT_DIR/chatgpt_server.py"
VENV_PY="$ROOT_DIR/.venv/bin/python3"

mkdir -p "$APP_DIR"

export CHAT_SERVER_PORT="${CHAT_SERVER_PORT:-5001}"
export CHAT_SERVER_HOST="${CHAT_SERVER_HOST:-127.0.0.1}"
export PYTHONUNBUFFERED=1
export CHAT_FRONTEND_APP_DIR="$APP_DIR"
export CHAT_FRONTEND_HTML="$APP_DIR/chat.html"
export CHAT_SOURCE_ROOT="$ROOT_DIR"

MODE="${CHAT_BACKEND_MODE:-auto}"

if [[ "$MODE" != "lightweight" && -f "$FULL_BACKEND_SCRIPT" ]]; then
  if [[ -x "$VENV_PY" ]]; then
    cd "$PROJECT_DIR"
    exec "$VENV_PY" "$FULL_BACKEND_SCRIPT"
  elif command -v python3 >/dev/null 2>&1; then
    cd "$PROJECT_DIR"
    exec "$(command -v python3)" "$FULL_BACKEND_SCRIPT"
  fi
fi

echo "[warn] full backend unavailable, fallback to lightweight frontend server" >&2
if [[ -x /usr/local/bin/python3 ]]; then
  exec /usr/local/bin/python3 "$APP_DIR/lightweight_chat_frontend_server.py"
fi
exec "$(command -v python3)" "$APP_DIR/lightweight_chat_frontend_server.py"
