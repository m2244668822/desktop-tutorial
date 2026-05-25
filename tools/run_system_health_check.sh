#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="$ROOT_DIR/reports"
TS="$(date +%Y%m%d_%H%M%S)"
TEXT_OUT="$REPORT_DIR/system_health_${TS}.txt"
JSON_OUT="$REPORT_DIR/system_health_${TS}.json"

mkdir -p "$REPORT_DIR"

python3 "$ROOT_DIR/tools/system_health_check.py" | tee "$TEXT_OUT"
python3 "$ROOT_DIR/tools/system_health_check.py" --json > "$JSON_OUT"

echo
echo "[ok] text report: $TEXT_OUT"
echo "[ok] json report: $JSON_OUT"
