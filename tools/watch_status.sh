#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR_SCRIPT="$ROOT_DIR/tools/live_status_monitor.py"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

if [[ ! -f "$MONITOR_SCRIPT" ]]; then
  echo "[error] monitor script not found: $MONITOR_SCRIPT" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$MONITOR_SCRIPT" "$@"
