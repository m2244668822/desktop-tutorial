#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_SLUG="${REPO_SLUG:-m2244668822/desktop-tutorial}"
BASE_URL="${BASE_URL:-http://127.0.0.1:5001}"
SQLITE_PATH="${SQLITE_PATH:-instance/chat_history.db}"
POSTGRES_URL="${POSTGRES_URL:-${APP_DATABASE_URL:-}}"
STRICT="${STRICT:-0}"

cd "$PROJECT_ROOT"

ARGS=(
  --project-root "$PROJECT_ROOT"
  --repo "$REPO_SLUG"
  --base-url "$BASE_URL"
  --sqlite-path "$SQLITE_PATH"
)

if [[ -n "${POSTGRES_URL}" ]]; then
  ARGS+=(--postgres-url "$POSTGRES_URL")
fi

if [[ "${STRICT}" == "1" ]]; then
  ARGS+=(--strict)
fi

python3 tools/verify_repo_and_db.py \
  "${ARGS[@]}"
