#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UID_NUM="$(id -u)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT/logs/launchagents"
LAUNCH_LOG_DIR="$HOME/Library/Logs/Perob"
BACKEND_LABEL="com.user.perob-backend"
HTTPS_LABEL="com.user.perob-https"
SERVICE_PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
HTTPS_LISTEN_HOST="${PEROB_HTTPS_LISTEN_HOST:-127.0.0.1}"
TRUSTED_PYTHON="${PEROB_CREDENTIAL_PYTHON:-/usr/local/bin/python3}"

mkdir -p "$LAUNCH_DIR" "$LOG_DIR" "$LAUNCH_LOG_DIR"
ARCHIVE_DIR="$LAUNCH_DIR/archive/perob-$(date +%Y%m%d-%H%M%S)"

MANAGED_PYTHON=""
for candidate in "$ROOT"/.python-installations/cpython-3.12*/bin/python3.12; do
  if [[ -x "$candidate" ]]; then
    MANAGED_PYTHON="$candidate"
    break
  fi
done

PYTHON_BIN=""
for candidate in \
  "$ROOT/.venv312/bin/python3" \
  "$ROOT/.venv312/bin/python" \
  "$MANAGED_PYTHON" \
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

if [[ -z "$PYTHON_BIN" ]]; then
  echo "[error] no runnable macOS Python found" >&2
  exit 1
fi
if [[ ! -x "$TRUSTED_PYTHON" ]]; then
  TRUSTED_PYTHON="$PYTHON_BIN"
fi

PY_VERSION="$("$PYTHON_BIN" - <<'PY' 2>/dev/null || true
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
if [[ -n "$PY_VERSION" ]]; then
  case "$PY_VERSION" in
    3.14|3.15|3.16|3.17|3.18|3.19)
      echo "[warn] Python ${PY_VERSION} may trigger Pydantic v1 compatibility warnings; prefer .venv312 or .venv311" >&2
      ;;
  esac
fi

cat > "$LAUNCH_DIR/${BACKEND_LABEL}.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${BACKEND_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${TRUSTED_PYTHON}</string>
    <string>${ROOT}/tools/launch_trevor_backend.py</string>
    <string>--python</string><string>${PYTHON_BIN}</string>
    <string>--</string>
    <string>-u</string>
    <string>${ROOT}/desktop_chat_app.py</string>
    <string>web</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>5001</string>
    <string>--energy-lite</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>${SERVICE_PATH}</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
    <key>PYTHONUTF8</key><string>1</string>
    <key>OPENCLAW_ENABLED</key><string>true</string>
    <key>TREVOR_GEMINI_FREE_TIER_CONFIRMED</key><string>true</string>
    <key>TREVOR_GROQ_FREE_TIER_CONFIRMED</key><string>true</string>
    <key>TREVOR_WEB_SEARCH_ENABLED</key><string>true</string>
    <key>TREVOR_DELIBERATION_ROLLOUT</key><string>shadow</string>
  </dict>
  <key>WorkingDirectory</key><string>${HOME}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${LAUNCH_LOG_DIR}/perob-backend.out</string>
  <key>StandardErrorPath</key><string>${LAUNCH_LOG_DIR}/perob-backend.err</string>
</dict>
</plist>
EOF

cat > "$LAUNCH_DIR/${HTTPS_LABEL}.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${HTTPS_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>${ROOT}/tools/https_local_proxy.py</string>
    <string>--listen-host</string><string>${HTTPS_LISTEN_HOST}</string>
    <string>--listen-port</string><string>5443</string>
    <string>--upstream-host</string><string>127.0.0.1</string>
    <string>--upstream-port</string><string>5001</string>
    <string>--certfile</string><string>${ROOT}/certs/local-https.crt</string>
    <string>--keyfile</string><string>${ROOT}/certs/local-https.key</string>
    <string>--external-https-base</string><string>https://perob.com:5443</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>${SERVICE_PATH}</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
    <key>PYTHONUTF8</key><string>1</string>
  </dict>
  <key>WorkingDirectory</key><string>${HOME}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${LAUNCH_LOG_DIR}/perob-https.out</string>
  <key>StandardErrorPath</key><string>${LAUNCH_LOG_DIR}/perob-https.err</string>
</dict>
</plist>
EOF

for stale in com.user.perob-backend.local com.user.perob-https.local; do
  launchctl bootout "gui/${UID_NUM}/${stale}" >/dev/null 2>&1 || true
  if [[ -f "$LAUNCH_DIR/${stale}.plist" ]]; then
    mkdir -p "$ARCHIVE_DIR"
    mv "$LAUNCH_DIR/${stale}.plist" "$ARCHIVE_DIR/${stale}.plist"
  fi
done
launchctl bootout "gui/${UID_NUM}/${BACKEND_LABEL}" >/dev/null 2>&1 || true
launchctl bootout "gui/${UID_NUM}/${HTTPS_LABEL}" >/dev/null 2>&1 || true

plutil -lint "$LAUNCH_DIR/${BACKEND_LABEL}.plist"
plutil -lint "$LAUNCH_DIR/${HTTPS_LABEL}.plist"

echo "[ok] installed canonical Perob LaunchAgents"
echo "[info] python=${PYTHON_BIN}"
echo "[info] credential_python=${TRUSTED_PYTHON}"
if [[ -d "$ARCHIVE_DIR" ]]; then
  echo "[info] archived stale LaunchAgents: ${ARCHIVE_DIR}"
fi
echo "[next] bash tools/manage_perob_stack.sh restart"
echo "[note] external-volume workspaces default to Terminal-safe background mode"
echo "[note] after granting Python Full Disk Access, opt in with PEROB_USE_LAUNCHAGENT=1"
