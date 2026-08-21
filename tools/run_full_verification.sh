#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN=""
  for candidate in \
    "$ROOT/.venv312/bin/python3" \
    "$ROOT/.venv312/bin/python" \
    "$ROOT/.venv311/bin/python3" \
    "$ROOT/.venv311/bin/python" \
    "$(command -v python3.12 || true)" \
    "$(command -v python3.11 || true)" \
    "$ROOT/.venv/bin/python3" \
    "$ROOT/.venv/bin/python" \
    "$(command -v python3 || true)"
  do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
[[ -n "$PYTHON_BIN" ]] || { echo "[verify] Python runtime not found" >&2; exit 1; }
STRICT="${STRICT:-0}"

echo "[verify] Python syntax"
"$PYTHON_BIN" -m py_compile \
  core/web_server.py \
  core/openclaw_adapter.py \
  core/agent_collaboration_audit.py \
  core/knowledge_hub.py \
  desktop_chat_app.py \
  chatgpt_server.py \
  SYSTEM_DIAGNOSTIC.py \
  tools/agent_git_autopilot.py \
  tools/generate_system_framework_master_report.py \
  tools/generate_agent_collaboration_review.py

echo "[verify] Shell syntax"
bash -n \
  start_desktop_chat_app.sh \
  tools/fix_https_cert_perob.sh \
  tools/install_perob_launchagents.sh \
  tools/manage_perob_stack.sh \
  tools/normalize_perob_hosts.sh \
  tools/start_web_server_5001.sh

echo "[verify] Unit contracts"
"$PYTHON_BIN" -m unittest \
  tests.test_desktop_web_compat_routes \
  tests.test_agent_memory_aeg_status \
  tests.test_prophet_dialog_first \
  tests.test_prophet_engineer_bridge \
  tests.test_perob_mainline_health_contract \
  tests.test_openclaw_forwarding_contract \
  tests.test_agent_collaboration_training_contract \
  tests.test_agent_collaboration_conflict_regression \
  tests.test_prophet_contextual_miss \
  -v

echo "[verify] Git whitespace"
git diff --check

echo "[verify] Repository object integrity"
git fsck --full --strict --no-reflogs

if curl -fsS --max-time 3 http://127.0.0.1:5001/health/live >/dev/null 2>&1; then
  echo "[verify] Runtime health"
  curl -fsS --max-time 5 http://127.0.0.1:5001/health/live
  printf '\n'
  curl -fsS --max-time 10 http://127.0.0.1:5001/health/ready
  printf '\n'
elif [[ "$STRICT" == "1" ]]; then
  echo "[verify] Runtime health failed: server is not running" >&2
  exit 1
else
  echo "[verify] Runtime health skipped: server is not running"
fi

echo "[verify] Completed"
