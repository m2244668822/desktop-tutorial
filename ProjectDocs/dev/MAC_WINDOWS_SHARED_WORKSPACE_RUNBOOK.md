# Mac / Windows Shared Workspace Runbook

Last updated: 2026-05-23

This runbook is the clean UTF-8 handoff guide for running the same workspace on macOS and Windows.
The goal is simple: keep data safe, avoid path confusion, and let the agent system know where its memory lives.

## Current Verified Status

- Windows workspace: `G:\城城城程式`
- Main web service: `http://127.0.0.1:5001`
- Knowledge manifest: `data/knowledge_hub/manifest.json`
- ChatGPT long-term database: ready
- SQLite memory layer: ready
- FAISS semantic index: ready
- Indexed memory items: 446
- Task board: pending 0, running 0
- n8n: use the Windows CMD channel, do not mix it into the web startup script
- FFmpeg: not installed yet; winget source is reachable, but download stalled in this environment

## Everyday Explanation

- The workspace is the office.
- `data/` is the active desk where the running app reads and writes.
- `data_hdd_storage/` is the storage room / cold backup.
- ChatGPT DB is the big box of original notes.
- SQLite is the organized card cabinet.
- FAISS is the fast librarian who finds related cards by meaning, not just exact words.
- `manifest.json` is the sticky note on the front door telling both Mac and Windows where the library is.

If the sticky note is missing but SQLite and FAISS are still present, the data is not gone. It means the handoff card needs to be regenerated.

## Source Of Truth

- Program entry: `desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite`
- Windows bootstrap: `tools/windows_bootstrap.ps1`
- Knowledge sync: `tools/sync_knowledge_hub.py`
- Knowledge status API: `core/knowledge_hub.py`
- Workflow status integration: `core/workflow_runtime.py`
- Agent memory persistence: `tools/agent_memory_manager.py`
- macOS sync channel: `tools/sync_ssd_to_hdd.sh`
- Windows sync channel: `tools/sync_workspace_windows.ps1`

## Windows Startup

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite
```

Open:

```text
http://127.0.0.1:5001/chat_shell
```

## macOS Startup

```bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
python3 desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite
```

If macOS uses a different mount path, regenerate the manifest after mounting the workspace:

```bash
python3 tools/sync_knowledge_hub.py
```

## n8n CMD Channel

The "CMD channel" means n8n starts through Windows `cmd.exe`, not PowerShell.

Reason:

- PowerShell can block `npm.ps1` or `n8n.ps1` because of execution policy.
- `cmd /c n8n` avoids that script-policy trap.
- n8n is a long-running automation service, so it should stay separate from the web app startup.

Use:

```powershell
.\tools\start_n8n_windows.cmd
```

or:

```powershell
cmd /c n8n
```

## Cross-System Compatibility Pattern

There is no magic plugin that perfectly translates all Mac and Windows code. The reliable method is an adapter layer:

- Use `pathlib` and `ProjectPaths` in Python instead of hard-coded `/Volumes/...` or `G:\...`.
- Keep Mac shell scripts in `.sh`.
- Keep Windows launch/sync scripts in `.cmd` or `.ps1`.
- Tag sync channels clearly:
  - `CHANNEL_TAG: mac-sync`
  - `CHANNEL_TAG: windows-sync`
- Regenerate `data/knowledge_hub/manifest.json` on the machine that is currently running the workspace.

## Daily Health Check

Windows:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe tools\sync_knowledge_hub.py
.\.venv\Scripts\python.exe -m py_compile desktop_chat_app.py core\web_server.py core\knowledge_hub.py core\workflow_runtime.py
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5001/status
```

macOS:

```bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
python3 tools/sync_knowledge_hub.py
python3 -m py_compile desktop_chat_app.py core/web_server.py core/knowledge_hub.py core/workflow_runtime.py
curl http://127.0.0.1:5001/status
```

Expected:

- `ChatGPT DB: ready`
- `SQLite: ready`
- `FAISS: ready`
- `total_items` greater than 0
- `/status` returns `ok: true`

## Git Integrity Check

```bash
git fsck --full --no-reflogs
git count-objects -vH
git branch -vv
git for-each-ref refs/remotes/origin --format='%(refname:short) -> %(objectname:short)'
```

Notes:

- `empty object = 0` means the empty-object corruption has been cleared.
- Still check branch tracking, because a clean object store does not prove every branch is correctly connected.
- Do not run `git reset --hard` unless the current work has been backed up and explicitly approved.

## Do Not Do These

- Do not rename the Chinese workspace path to question marks or ASCII just to make one tool happy.
- Do not copy an old macOS `/Volumes/...` manifest directly into Windows as truth.
- Do not mix n8n startup into the web app script.
- Do not delete `data/`, `data_hdd_storage/`, or `500/llama32-chat/data/` to "clean up".
- Do not use `git reset --hard` or `git checkout --` as a repair shortcut.
- Do not read a JSON file while another process is writing it unless the writer uses atomic replace.

## Optional Tools

- Cursor: optional editor integration.
- Docker Desktop: only needed if the workflow uses containers.
- FFmpeg: needed for MP4 export. Current environment reached the GitHub release source, but download speed was too low to finish during this run.

