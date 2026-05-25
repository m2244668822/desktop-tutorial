#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

/usr/local/bin/python3 tools/generate_weekly_co_read_summary.py --days 7

echo "✅ 共讀每週摘要已完成（7 天）"
