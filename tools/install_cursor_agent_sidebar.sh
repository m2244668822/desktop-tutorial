#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${REPO_ROOT}/cursor-agent-sidebar-extension"
CURSOR_EXT_ROOT="${HOME}/.cursor/extensions"
CURSOR_SETTINGS="${HOME}/Library/Application Support/Cursor/User/settings.json"
ENV_FILE="${REPO_ROOT}/.sync_user_project/.env"

EXT_PUBLISHER="chengcheng-local"
EXT_NAME="cursor-agent-sidebar"
EXT_VERSION="0.0.1"
EXT_ID="${EXT_PUBLISHER}.${EXT_NAME}"
EXT_DIR_NAME="${EXT_ID}-${EXT_VERSION}-universal"
DST_DIR="${CURSOR_EXT_ROOT}/${EXT_DIR_NAME}"
EXT_INDEX_JSON="${CURSOR_EXT_ROOT}/extensions.json"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "[error] missing extension source: $SRC_DIR" >&2
  exit 1
fi

mkdir -p "$CURSOR_EXT_ROOT"
rm -rf "$DST_DIR"
cp -R "$SRC_DIR" "$DST_DIR"

REPO_ROOT="$REPO_ROOT" \
CURSOR_EXT_ROOT="$CURSOR_EXT_ROOT" \
CURSOR_SETTINGS="$CURSOR_SETTINGS" \
ENV_FILE="$ENV_FILE" \
DST_DIR="$DST_DIR" \
EXT_INDEX_JSON="$EXT_INDEX_JSON" \
EXT_ID="$EXT_ID" \
EXT_VERSION="$EXT_VERSION" \
python3 - <<'PY'
from pathlib import Path
import json
import os
import time
import uuid

cursor_root = Path(os.environ["CURSOR_EXT_ROOT"])
settings_path = Path(os.environ["CURSOR_SETTINGS"])
env_path = Path(os.environ["ENV_FILE"])
dst = Path(os.environ["DST_DIR"])
ext_index = Path(os.environ["EXT_INDEX_JSON"])
ext_id = os.environ["EXT_ID"]
ext_version = os.environ["EXT_VERSION"]

pkg_path = dst / "package.json"
pkg = json.loads(pkg_path.read_text("utf-8"))
pkg["publisher"] = "chengcheng-local"
pkg["name"] = "cursor-agent-sidebar"
pkg["version"] = ext_version
pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if ext_index.exists():
    try:
        data = json.loads(ext_index.read_text("utf-8"))
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
else:
    data = []

entry = {
    "identifier": {"id": ext_id, "uuid": str(uuid.uuid4())},
    "version": ext_version,
    "location": {"$mid": 1, "path": str(dst), "scheme": "file"},
    "relativeLocation": dst.name,
    "metadata": {
        "installedTimestamp": int(time.time() * 1000),
        "source": "local",
        "id": str(uuid.uuid4()),
        "publisherDisplayName": "chengcheng-local",
        "targetPlatform": "universal",
        "updated": False,
        "private": False,
        "isPreReleaseVersion": False,
        "hasPreReleaseVersion": False,
    },
}

for index, item in enumerate(data):
    if ((item.get("identifier") or {}).get("id") == ext_id):
        data[index] = entry
        break
else:
    data.append(entry)

ext_index.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

settings_path.parent.mkdir(parents=True, exist_ok=True)
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text("utf-8"))
        if not isinstance(settings, dict):
            settings = {}
    except Exception:
        settings = {}
else:
    settings = {}

env = {}
if env_path.exists():
    for line in env_path.read_text("utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()

port = env.get("CHAT_SERVER_PORT") or "5001"
settings["cursorAgentSidebar.serverBaseUrl"] = f"http://127.0.0.1:{port}"
if env.get("SERVER_API_TOKEN"):
    settings["cursorAgentSidebar.serverToken"] = env["SERVER_API_TOKEN"]
if env.get("CHATGPT_BRIDGE_INGEST_TOKEN"):
    settings["cursorAgentSidebar.bridgeToken"] = env["CHATGPT_BRIDGE_INGEST_TOKEN"]
settings.setdefault("workbench.activityBar.visible", True)

settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("installed", dst)
print("registered", ext_id)
print("settings", settings_path)
PY

echo "[ok] Cursor Agent Sidebar installed as local extension: $EXT_ID"
echo "[ok] reopen Cursor or run: Developer: Reload Window"
