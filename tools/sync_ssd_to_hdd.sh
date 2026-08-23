#!/usr/bin/env bash
set -euo pipefail

# CHANNEL_TAG: mac-sync
# PLATFORM: macOS/Linux (bash + rsync required)
# COMPANION_WINDOWS_CHANNEL: tools/sync_workspace_windows.ps1
# PURPOSE: Sync workspace data from fast SSD path to backup HDD path.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'USAGE'
Usage:
  ./tools/sync_ssd_to_hdd.sh <SOURCE_DIR> <DEST_DIR>

Examples:
  ./tools/sync_ssd_to_hdd.sh \
    "/Volumes/YourSSD/workspace" \
    "/Volumes/YourHDD/workspace_full_backup_$(date +%Y%m%d)"

Notes:
  - This script is macOS/Linux channel.
  - Windows channel uses: tools/sync_workspace_windows.ps1
USAGE
}

SOURCE_DIR="${1:-${SOURCE_DIR:-}}"
DEST_DIR="${2:-${DEST_DIR:-}}"

if [[ -z "$SOURCE_DIR" || -z "$DEST_DIR" ]]; then
  usage
  exit 2
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "[error] SOURCE_DIR not found: $SOURCE_DIR"
  exit 2
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "[error] rsync not found. Install rsync first."
  exit 2
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="$SOURCE_DIR/reports"
LOG_FILE="$REPORT_DIR/storage_sync_mac_${STAMP}.log"
CASE_JSON="$REPORT_DIR/case_collision_report_mac_${STAMP}.json"

mkdir -p "$DEST_DIR" "$REPORT_DIR"

echo "== SSD -> HDD Sync (macOS channel) ==" | tee "$LOG_FILE"
echo "SOURCE: $SOURCE_DIR" | tee -a "$LOG_FILE"
echo "DEST  : $DEST_DIR" | tee -a "$LOG_FILE"
echo "ROOT  : $ROOT" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

PY="$(command -v python3 || command -v python || true)"
if [[ -n "$PY" && -f "$ROOT/tools/check_case_collisions.py" ]]; then
  echo "[1/4] Scan case-insensitive collisions..." | tee -a "$LOG_FILE"
  if "$PY" "$ROOT/tools/check_case_collisions.py" "$SOURCE_DIR" --json-out "$CASE_JSON" | tee -a "$LOG_FILE"; then
    echo "Case scan: clean" | tee -a "$LOG_FILE"
  else
    echo "Case scan: collisions found (see JSON report)" | tee -a "$LOG_FILE"
  fi
else
  echo "[1/4] Skip case scan (python/check_case_collisions.py unavailable)" | tee -a "$LOG_FILE"
fi

echo | tee -a "$LOG_FILE"
echo "[2/4] Sync files..." | tee -a "$LOG_FILE"
time rsync -aH --delete --stats "$SOURCE_DIR/" "$DEST_DIR/" | tee -a "$LOG_FILE"

echo | tee -a "$LOG_FILE"
echo "[3/4] Verify drift by dry-run..." | tee -a "$LOG_FILE"
DRIFT_COUNT="$(
  rsync -aH --delete --dry-run --itemize-changes "$SOURCE_DIR/" "$DEST_DIR/" \
    | wc -l \
    | tr -d ' '
)"
echo "Dry-run drift count: ${DRIFT_COUNT}" | tee -a "$LOG_FILE"
if [[ "${DRIFT_COUNT}" != "0" ]]; then
  echo "Top drift items:" | tee -a "$LOG_FILE"
  rsync -aH --delete --dry-run --itemize-changes "$SOURCE_DIR/" "$DEST_DIR/" \
    | sed -n '1,20p' \
    | tee -a "$LOG_FILE"
fi

echo | tee -a "$LOG_FILE"
echo "[4/4] Complete" | tee -a "$LOG_FILE"
echo "Log  : ${LOG_FILE}" | tee -a "$LOG_FILE"
echo "Case : ${CASE_JSON}" | tee -a "$LOG_FILE"
