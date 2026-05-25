#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN=""
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON_BIN=".venv/Scripts/python.exe"
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "❌ 找不到 .venv/bin/python"
  echo "   也找不到 .venv/Scripts/python.exe"
  echo "   請先建立或修復 .venv（macOS/Linux 或 Windows）。"
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
