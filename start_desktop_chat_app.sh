#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN=""
for candidate in \
  ".venv312/bin/python3" \
  ".venv312/bin/python" \
  ".venv/bin/python3" \
  ".venv/bin/python" \
  "$(command -v python3 || true)"
do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "❌ 找不到可執行的 macOS/Linux Python。"
  echo "   Windows 的 .venv/Scripts/python.exe 不可在 macOS 直接使用。"
  exit 1
fi

MODE="${1:-web}"
if [ "$MODE" = "web" ] || [ "$MODE" = "desktop" ] || [ "$MODE" = "health" ]; then
  shift || true
  echo "🚀 單一主程式入口：system_main.py ($MODE)"
  exec "$PYTHON_BIN" system_main.py "$MODE" "$@"
fi

echo "ℹ️ 未指定合法模式，預設改為 web。可用：web / desktop / health"
exec "$PYTHON_BIN" system_main.py web "$@"
