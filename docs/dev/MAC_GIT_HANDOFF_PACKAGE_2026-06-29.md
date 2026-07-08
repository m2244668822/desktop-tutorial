# Mac/Git Handoff Package - 2026-06-29

## Current Branch

Use this branch when continuing from macOS:

```bash
git fetch origin
git checkout codex/git-governance-20260517
git pull
git log -5 --oneline --decorate
```

If this document is present after pulling, the branch includes the foundation health, n8n preflight, OpenClaw governance, and mobile chat shell smoke improvements.

## Path Reality

The Windows repo used for this handoff is:

```text
E:\智能體\城城城程式
```

`F:\城城城程式` is not present in the current Windows environment. If Codex, PowerShell, Terminal, or a Mac shell opens in a missing path, commands can fail before Python or Git has a chance to run. See:

- `docs/dev/SHELL_WORKSPACE_PATH_TROUBLESHOOTING_2026-07-04.md`

On macOS, use the actual clone path, for example:

```bash
cd /Volumes/<your-volume>/<your-clone>
git status -sb
```

Do not reuse Windows absolute paths inside scripts or manifests. Regenerate path-sensitive manifests from the Mac repo root.

## Mac Bootstrap

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python desktop_chat_app.py web --host 127.0.0.1 --port 5001 --energy-lite
```

In a second terminal:

```bash
export BROWSER_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python tools/chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 390 --height 844
python tools/chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 1440 --height 1000
```

Then run:

```bash
python tools/foundation_health_check.py --browser-smoke required
python tools/n8n_workflow_preflight.py --allow-blockers
python -m pytest tests/test_foundation_health_check.py tests/test_frontend_sync_contract.py tests/test_n8n_workflow_preflight.py --tb=short
```

The foundation report now has a top-level `next_actions` list. To print it:

```bash
python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path("reports/foundation_health_latest.json").read_text())
for item in report.get("next_actions", []):
    print(f"[{item['priority']}] {item['source']}: {item['summary']}")
PY
```

Read `ok` and `attention_required` together. `ok=true` means the configured checks passed; `attention_required=true` means there are still follow-up actions such as n8n activation blockers.

If n8n preflight is still blocked, open the JSON report and follow `remediation_plan`:

```bash
python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path("reports/n8n_workflow_preflight_latest.json").read_text())
for item in report.get("remediation_plan", []):
    print(f"- {item['code']}: {item['summary']}")
PY
```

## Windows Validation Already Added

| Area | Current Gate |
|---|---|
| workspace context | `foundation_health_check.py` reports cwd, git root, and required files |
| frontend static contract | canonical chat shell tokens plus mobile layout contract |
| browser smoke | headless Chrome/Edge checks DOM, console, runtime exceptions, and layout |
| n8n workflow | preflight blocks activation and emits a structured remediation plan |
| OpenClaw | `openclaw_runtime` verifies CLI, local gateway listener, and `/healthz` |

## n8n Status

The Xiaobian workflow source spec has been hardened with timeout, cost controls, error policy, webhook header auth, controlled FFmpeg output, and `FFMPEG_PATH` / `XIAOBIAN_FFMPEG_PATH` override support. Activation is still blocked until:

| Blocker | Action |
|---|---|
| Gemini/OpenAI credentials | Configure provider credentials in n8n |
| n8n credential DB | Ensure `credentials_entity` is non-empty |
| FFmpeg | Install and expose `ffmpeg` on PATH, or set `FFMPEG_PATH` / `XIAOBIAN_FFMPEG_PATH` before starting n8n |
| live imported workflow | Re-import the hardened source spec so FFmpeg path override support reaches n8n DB |
| manual execution | Run only after preflight reports `ready_for_activation` |

## OpenClaw Status

Current Windows evidence shows local execution support is ready:

```text
health=ready
decision_state=running
local_execution.supported=true
gateway.url=http://127.0.0.1:18789/healthz
```

Mutation remains governed:

```text
auto_start_allowed=false
prophet_required_for_mutation=true
```

On Mac, rerun `python tools/foundation_health_check.py --browser-smoke required` and confirm `openclaw_runtime: ready` before treating OpenClaw as locally executable there.

## Git Scope

Generated reports normally stay uncommitted:

```bash
git restore --staged reports/AEG_SHARED_REPORT.md 2>/dev/null || true
```

Before pushing from Mac:

```bash
git status -sb
git diff --stat
python -m pytest tests/test_foundation_health_check.py tests/test_frontend_sync_contract.py --tb=short
git push origin codex/git-governance-20260517
```

## Next Best Work On Mac

1. Verify the Mac clone path and run `git status -sb`.
2. Start the gateway and run browser smoke at mobile and desktop widths.
3. Run `tools/foundation_health_check.py --browser-smoke required`.
4. Fix n8n activation blockers before enabling the workflow.
5. Keep runtime reports separate from source commits.
