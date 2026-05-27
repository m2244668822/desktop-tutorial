#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/tools/sync_chatgpt_custom_instructions.py" --workspace "$ROOT_DIR" "$@"
fi
exec python3 "$ROOT_DIR/tools/sync_chatgpt_custom_instructions.py" --workspace "$ROOT_DIR" "$@"
