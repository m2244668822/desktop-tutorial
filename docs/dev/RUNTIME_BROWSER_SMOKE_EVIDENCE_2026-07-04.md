# Runtime And Browser Smoke Evidence - 2026-07-04

## Purpose

This note records the July 4 Windows runtime proof after the foundation health and next-action gates were added. It is evidence, not a replacement for rerunning the checks on macOS.

## Environment

| Item | Value |
|---|---|
| Repo | `E:\智能體\城城城程式` |
| Branch | `codex/git-governance-20260517` |
| Gateway | `127.0.0.1:5001` |
| n8n editor | `5678` |
| n8n task broker | `5679` |
| Ollama | `11434` |

## Commands Run

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\enforce_single_entry_gateway.ps1
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 390 --height 844
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 768 --height 1024
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 1440 --height 1000
python tools\foundation_health_check.py --browser-smoke required --json-out reports\foundation_runtime_all_services.json
```

Ollama was started with:

```powershell
ollama serve
```

## Runtime Result

| Check | Result | Evidence |
|---|---|---|
| workspace context | OK | `workspace_context: ready` |
| ports | OK | `5001`, `5678`, `5679`, and `11434` listening |
| gateway | OK | `gateway: ready_with_openclaw_stopped` |
| n8n | OK | `/healthz`, `/healthz/readiness`, and broker `/healthz` returned 200 |
| n8n preflight | OK inventory, blocked activation | `blocked_for_activation` with remediation plan |
| Knowledge Hub | OK | `knowledge_hub: ready` |
| frontend static contract | OK | `frontend_static_contract: ready` |
| browser smoke | OK | `browser_smoke: ready` |

Port evidence:

```text
127.0.0.1:5001  listening
0.0.0.0/[::]:5678 listening
127.0.0.1:5679 listening
127.0.0.1:11434 listening
```

## Frontend Viewport Smoke

| Viewport | Result |
|---|---|
| `390x844` | PASS |
| `768x1024` | PASS |
| `1440x1000` | PASS |

All three reports returned `status=ready` and `ok=true`.

## n8n Startup Observation

n8n needed roughly 132 seconds from watchdog start request to listening:

```text
2026-07-04 08:27:35 started n8n cmd_pid=12124 startup_wait=180s telemetry=disabled
2026-07-04 08:29:47 n8n listening after start
```

The 180 second watchdog wait is still justified. Running the foundation check too early can show n8n as temporarily degraded even when the watchdog is still within its startup window.

## Remaining Work

| Gap | Priority | Next Action |
|---|---|---|
| n8n provider credentials | P1 | Bind Gemini/OpenAI credentials in n8n |
| n8n credential DB empty | P1 | Create at least one provider credential |
| FFmpeg not on PATH | P1 | Install FFmpeg and verify `ffmpeg -version` |
| live workflow stale | P1 | Re-import `docs/superpowers/specs/n8n-workflow-xiaobian-video.json` |
| OpenClaw governed-stopped | P1 | Keep stopped unless governance approval allows start |

## Interpretation

The runtime is operational for gateway, frontend, n8n visibility, Knowledge Hub, and browser smoke. It is not production-ready for Xiaobian n8n workflow activation until the preflight blockers are cleared.
