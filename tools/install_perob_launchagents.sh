#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UID_NUM="$(id -u)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT/logs/launchagents"
LAUNCH_LOG_DIR="$HOME/Library/Logs/Perob"
BACKEND_LABEL="com.user.perob-backend"
HTTPS_LABEL="com.user.perob-https"

mkdir -p "$LAUNCH_DIR" "$LOG_DIR" "$LAUNCH_LOG_DIR"
ARCHIVE_DIR="$LAUNCH_DIR/archive/perob-$(date +%Y%m%d-%H%M%S)"

PYTHON_BIN=""
for candidate in \
  "$ROOT/.venv312/bin/python3" \
  "$ROOT/.venv312/bin/python" \
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

cat > "$LAUNCH_DIR/${BACKEND_LABEL}.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${BACKEND_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>${ROOT}/system_main.py</string>
    <string>web</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>5001</string>
    <string>--energy-lite</string>
    <string>--skip-health</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key><string>1</string>
    <key>PYTHONUTF8</key><string>1</string>
    <key>OPENCLAW_ENABLED</key><string>true</string>
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
    <string>--listen-host</string><string>0.0.0.0</string>
    <string>--listen-port</string><string>5443</string>
    <string>--upstream-host</string><string>127.0.0.1</string>
    <string>--upstream-port</string><string>5001</string>
    <string>--certfile</string><string>${ROOT}/certs/local-https.crt</string>
    <string>--keyfile</string><string>${ROOT}/certs/local-https.key</string>
    <string>--external-https-base</string><string>https://perob.com:5443</string>
  </array>
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
if [[ -d "$ARCHIVE_DIR" ]]; then
  echo "[info] archived stale LaunchAgents: ${ARCHIVE_DIR}"
fi
echo "[next] bash tools/manage_perob_stack.sh restart"
echo "[note] external-volume workspaces default to Terminal-safe background mode"
echo "[note] after granting Python Full Disk Access, opt in with PEROB_USE_LAUNCHAGENT=1"
