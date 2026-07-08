# Shell And Workspace Path Troubleshooting - 2026-07-04

## Why Shell Commands Sometimes Cannot Run

The shell can fail before the command itself starts when its working directory does not exist. In this workspace the most common cause is a stale path from another machine or drive.

Current Windows reality:

```text
exists:  E:\智能體\城城城程式
missing: F:\城城城程式
```

If the tool starts PowerShell with `F:\城城城程式` as cwd, even simple commands like `git status` or `Get-Location` can fail with:

```text
目錄名稱無效。
```

That error is not a Git failure and not a Python failure. It means the process could not enter the requested directory.

## Quick Windows Probe

Run from any known-good directory such as `C:\Users\pc`:

```powershell
Get-Location
Get-PSDrive -PSProvider FileSystem | Select-Object Name,Root
Test-Path 'E:\智能體\城城城程式'
Test-Path 'F:\城城城程式'
Set-Location 'E:\智能體\城城城程式'
git status -sb
```

If `F:` is missing but a tool keeps using it, change the tool workspace root to `E:\智能體\城城城程式` or start commands with an explicit `workdir`.

## Quick macOS Probe

On Mac the same class of problem appears when an external volume is not mounted, the clone moved, or a symlink points to an old path:

```bash
pwd
ls /Volumes
test -d "/Volumes/<volume>/<clone>" && echo "repo exists"
cd "/Volumes/<volume>/<clone>"
git status -sb
```

If the repo is not there, find it:

```bash
find /Volumes "$HOME" -maxdepth 4 -name .git -type d 2>/dev/null
```

Then enter the parent directory of the `.git` folder.

## Shell Syntax Is Not Portable

Windows PowerShell, Windows `cmd.exe`, macOS Bash, and macOS Zsh do not share all syntax.

Common examples:

| Intent | PowerShell | Bash/Zsh |
|---|---|---|
| run Python from stdin | `@' ... '@ | python -` | `python - <<'PY' ... PY` |
| set one env var for one command | `$env:NAME='value'; python app.py` | `NAME=value python app.py` |
| path separator | `E:\repo\tools` | `/Volumes/disk/repo/tools` |
| executable venv Python | `.venv\Scripts\python.exe` | `.venv/bin/python` |

If a command fails before the app starts, first identify which shell is running:

```powershell
$PSVersionTable.PSVersion
```

```bash
echo "$SHELL"
```

Then translate the command instead of assuming the app broke.

## Repo-Level Check

Once inside the repo, run:

```bash
python tools/foundation_health_check.py --browser-smoke off
python tools/runtime_dependency_doctor.py --allow-missing
python tools/runtime_service_controller.py status
```

The `workspace_context` row records:

| Field | Meaning |
|---|---|
| `root` | repo root inferred from the script location |
| `cwd` | current shell directory |
| `cwd_inside_root` | whether the shell is inside the repo |
| `git_root` | Git's actual top-level directory |
| `required_files` | key files that prove this is the expected workspace |
| `env_paths` | path-like environment variables and whether they exist |

`ready_external_cwd` means the repo itself is valid but the command was launched from another directory. That is acceptable for absolute script calls, but it is a warning for handoff and automation.

`runtime_dependency_doctor.py` adds the next layer after the repo path is correct. It records whether the current shell can resolve the project venv, Node, n8n, FFmpeg, Ollama, and OpenClaw. If FFmpeg is present in one terminal but missing in another, compare the `shell_context.path_entries` and the failed probe's `resolution` block instead of changing app code.

`runtime_service_controller.py` is the controlled startup layer after dependencies are understood. Use `status` or `start --dry-run` first. OpenClaw startup is intentionally gated behind `--allow-openclaw-mutation`.

## What To Fix First

1. Fix missing cwd or stale volume paths before debugging app code.
2. Verify `git rev-parse --show-toplevel` matches the intended repo.
3. Run `python tools/runtime_dependency_doctor.py --allow-missing` and fix missing PATH/env dependencies before debugging services.
4. Run `python tools/runtime_service_controller.py status` before starting services.
5. Regenerate path-sensitive data from the real repo root:

```bash
python tools/sync_knowledge_hub.py
```

6. Rerun the foundation check.

This prevents a fake infrastructure problem from being caused by a shell that is simply standing in the wrong place.
