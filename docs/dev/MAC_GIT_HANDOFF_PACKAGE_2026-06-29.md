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
python tools/runtime_dependency_doctor.py --allow-missing
python tools/runtime_service_controller.py status
python tools/runtime_service_controller.py start --components web,n8n,ollama --dry-run
python tools/foundation_health_check.py --browser-smoke required
python tools/foundation_goal_audit.py --health-report reports/foundation_health_latest.json --allow-incomplete
python tools/n8n_workflow_preflight.py --allow-blockers
python -m pytest tests/test_foundation_health_check.py tests/test_runtime_dependency_doctor.py tests/test_runtime_service_controller.py tests/test_frontend_sync_contract.py tests/test_openclaw_bridge.py tests/test_n8n_workflow_preflight.py --tb=short
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

If n8n preflight is still blocked, open the JSON report and follow `credential_setup_plan` plus `remediation_plan`:

```bash
python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path("reports/n8n_workflow_preflight_latest.json").read_text())
plan = report.get("credential_setup_plan", {})
print(f"credential_setup_plan: {plan.get('status')}")
for item in plan.get("required_credentials", []):
    print(f"- credential {item['provider']}: bind {', '.join(item['nodes_needing_binding'] or item['nodes'])}")
for item in report.get("remediation_plan", []):
    print(f"- remediation {item['code']}: {item['summary']}")
PY
```

## Windows Validation Already Added

| Area | Current Gate |
|---|---|
| workspace context | `foundation_health_check.py` reports cwd, git root, and required files |
| runtime dependencies | `runtime_dependency_doctor.py` reports shell/PATH, `.venv`, Node, n8n, FFmpeg, Ollama, and OpenClaw readiness |
| service control | `runtime_service_controller.py` gives one status/start path for web, n8n, Ollama, and governed OpenClaw gateway |
| goal completion audit | `foundation_goal_audit.py` maps the health report back to the full foundation objective |
| frontend static contract | canonical chat shell tokens plus mobile layout contract |
| browser smoke | headless Chrome/Edge checks DOM, console, runtime exceptions, and layout |
| n8n workflow | preflight blocks activation and emits structured remediation plus credential setup plans |
| OpenClaw | `openclaw_runtime` verifies CLI, local gateway listener, and `/healthz` |

## n8n Status

The Xiaobian workflow source spec has been hardened with timeout, cost controls, error policy, webhook header auth, controlled FFmpeg output, and `FFMPEG_PATH` / `XIAOBIAN_FFMPEG_PATH` override support. The preflight now emits `credential_setup_plan` so the remaining manual n8n work is grouped by provider instead of scattered by node. Activation is still blocked until:

| Blocker | Action |
|---|---|
| Gemini/OpenAI credentials | Create real provider credentials in n8n, then bind Gemini Parser, DALL-E 3 Generator, and OpenAI TTS |
| n8n credential DB | Ensure `credentials_entity` is non-empty after creating real credentials |
| FFmpeg | Windows now resolves winget FFmpeg through `runtime_binary_locator.py`; on Mac install with Homebrew or set `FFMPEG_PATH` |
| live imported workflow | Cleared on Windows by re-importing the hardened source spec; re-import again on Mac if using a separate n8n DB |
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

On Mac, rerun `python tools/runtime_dependency_doctor.py --allow-missing`, `python tools/runtime_service_controller.py status`, and `python tools/foundation_health_check.py --browser-smoke required`; confirm `openclaw_local_execution: ready` and `openclaw_runtime: ready` before treating OpenClaw as locally executable there. Starting OpenClaw must use `python tools/runtime_service_controller.py start --components openclaw --allow-openclaw-mutation`.

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
2. Run `python tools/runtime_dependency_doctor.py --allow-missing` to separate shell/PATH dependency gaps from app bugs.
3. Run `python tools/runtime_service_controller.py status`, then dry-run service start before launching missing services.
4. Start the gateway and run browser smoke at mobile and desktop widths.
5. Run `tools/foundation_health_check.py --browser-smoke required`.
6. Run `tools/foundation_goal_audit.py --allow-incomplete`; do not claim complete while n8n activation is blocked.
7. Fix n8n activation blockers before enabling the workflow.
8. Keep runtime reports separate from source commits.
