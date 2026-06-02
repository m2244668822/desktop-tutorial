#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/logs/web_server_5001.log"
PIDFILE="$ROOT/logs/web_server_5001.pid"

mkdir -p "$ROOT/logs"
cd "$ROOT"

if lsof -nP -iTCP:5001 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[start] 5001 already listening"
  lsof -nP -iTCP:5001 -sTCP:LISTEN || true
  exit 0
fi

PY=""
for cand in "$ROOT/.venv312/bin/python3" "$ROOT/.venv312/bin/python" "$ROOT/.venv/bin/python3" "$ROOT/.venv/bin/python" "$(command -v python3 || true)"; do
  if [[ -n "$cand" && -x "$cand" ]]; then
    PY="$cand"
    break
  fi
done

if [[ -z "$PY" ]]; then
  echo "[start] python runtime not found"
  exit 1
fi

attempt=0
max_attempt=3
while [[ $attempt -lt $max_attempt ]]; do
  attempt=$((attempt + 1))
  echo "[start] attempt ${attempt}/${max_attempt} (python=$PY)"
  nohup "$PY" -u system_main.py web --host 127.0.0.1 --port 5001 --energy-lite --skip-health >"$LOG" 2>&1 &
  pid=$!
  echo "$pid" >"$PIDFILE"

  waited=0
  until lsof -nP -iTCP:5001 -sTCP:LISTEN >/dev/null 2>&1; do
    sleep 1
    waited=$((waited + 1))
    if [[ $waited -ge 30 ]]; then
      break
    fi
  done

  if lsof -nP -iTCP:5001 -sTCP:LISTEN >/dev/null 2>&1; then
    if curl -fsS -m 5 http://127.0.0.1:5001/health/live >/dev/null 2>&1; then
      echo "[start] success pid=$pid"
      lsof -nP -iTCP:5001 -sTCP:LISTEN || true
      curl -sS http://127.0.0.1:5001/health/ready || true
      exit 0
    fi
  fi

  echo "[start] failed, log tail:"
  tail -n 80 "$LOG" || true
  kill "$pid" >/dev/null 2>&1 || true
  sleep 1
done

echo "[start] all attempts failed"
exit 1
