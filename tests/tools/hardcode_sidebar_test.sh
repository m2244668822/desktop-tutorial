#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:5001"
ENV_FILE="/Volumes/智能體/城城城程式/.sync_user_project/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[error] .env not found: $ENV_FILE"
  exit 1
fi

TOKEN="$(awk -F= '/^SERVER_API_TOKEN=/{sub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' "$ENV_FILE")"
if [[ -z "${TOKEN:-}" ]]; then
  echo "[error] SERVER_API_TOKEN is empty in $ENV_FILE"
  exit 1
fi

echo "[info] hardcode test base_url=$BASE_URL"
echo "[info] token_loaded=yes length=${#TOKEN}"

run_case() {
  local name="$1"
  local auth_header="$2"
  local payload="$3"
  local code
  code="$(curl -sS -o "/tmp/${name}.json" -w "%{http_code}" \
    -X POST "$BASE_URL/sync" \
    -H "Content-Type: application/json" \
    -H "Authorization: $auth_header" \
    -d "$payload")"
  local status
  status="$(python3 - <<PY
import json
from pathlib import Path
p=Path('/tmp/${name}.json')
try:
    j=json.loads(p.read_text('utf-8'))
    print(j.get('status') or j.get('reason') or 'n/a')
except Exception:
    print('n/a')
PY
)"
  echo "[case] $name http=$code status=$status"
}

run_case "auth_raw" "$TOKEN" '{"type":"test"}'
run_case "auth_bearer" "Bearer $TOKEN" '{"type":"test"}'
run_case "auth_wrong" "Bearer hardcode_wrong_token" '{"type":"test"}'

FULL_SYNC_CODE="$(curl -sS -o /tmp/hardcode_fullsync.json -w "%{http_code}" \
  -X POST "$BASE_URL/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"type":"full_sync","async":true,"source":"hardcode_test"}')"

echo "$FULL_SYNC_CODE" > /tmp/hardcode_fullsync_code.txt

python3 - <<'PY'
import json
from pathlib import Path
p=Path('/tmp/hardcode_fullsync.json')
try:
    j=json.loads(p.read_text('utf-8'))
    print(f"[case] full_sync_async http={open('/tmp/hardcode_fullsync_code.txt').read().strip()} status={j.get('status')} job_id_present={bool(j.get('job_id'))}")
except Exception:
    print("[case] full_sync_async parse_failed")
PY

JOBS_CODE="$(curl -sS -o /tmp/hardcode_jobs.json -w "%{http_code}" \
  -X GET "$BASE_URL/sync/full-sync/jobs?limit=3" \
  -H "Authorization: Bearer $TOKEN")"

python3 - <<PY
import json
from pathlib import Path
j=json.loads(Path('/tmp/hardcode_jobs.json').read_text('utf-8'))
print(f"[case] jobs_list http=$JOBS_CODE count={j.get('count')} active={j.get('active_count')}")
PY

echo "[done] hardcode sidebar test completed"
