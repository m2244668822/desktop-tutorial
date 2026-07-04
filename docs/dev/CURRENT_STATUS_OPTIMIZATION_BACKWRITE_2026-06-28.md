# Current Status Optimization Backwrite - 2026-06-28

## Purpose

This note records the live Windows status after the June 28 optimization pass. It is meant to prevent older May notes from being treated as current runtime truth.

Update note: the OpenClaw runtime state in this file has been superseded by `docs/dev/RUNTIME_BROWSER_SMOKE_EVIDENCE_2026-07-04.md`, where OpenClaw local execution is verified as ready through `openclaw_runtime`.

## Updated Runtime Status

| Item | Status | Evidence |
|---|---|---|
| Main web gateway | UP | `http://127.0.0.1:5001/status` returned 200 |
| Gateway policy | UP | `http://127.0.0.1:5001/api/gateway/policy` returned 200 |
| n8n editor | UP | `http://127.0.0.1:5678/healthz` returned 200 |
| n8n task broker | UP | `http://127.0.0.1:5679/healthz` returned 200 |
| Ollama | UP | Port `11434` listening |
| OpenClaw CLI | Installed | `/api/get_status` reports `OpenClaw 2026.5.27 (27ae826)` |
| OpenClaw daemon | GOVERNED STOPPED | `/api/get_status` reports `daemon_state=stopped`, `health=governed_stopped`, and `decision_state=prophet_decision_required` |
| Chat shell route | UP | `GET /chat_shell` returned 200 and includes the new agent activity board/backoff contract |
| Test suite | PASS | `python -m pytest tests --tb=short` returned `79 passed` |
| Foundation checker | PASS WITH KNOWN GAPS | `tools/foundation_health_check.py --browser-smoke required` reports ports, gateway, n8n, Knowledge Hub, frontend contract, git, py_compile, and browser smoke |
| Browser smoke | PASS | Headless Chrome loaded `/chat_shell`, found no runtime exceptions/console errors, and wrote `reports/chat_shell_browser_smoke_latest.png` |
| n8n workflow preflight | BLOCKED FOR ACTIVATION | `tools/n8n_workflow_preflight.py` found activation blockers while keeping the imported workflow inactive |

## Changes Completed

- Rebuilt `data/knowledge_hub/manifest.json` and `data/knowledge_hub/README.md` with clean UTF-8 paths.
- Verified Knowledge Hub readiness: ChatGPT DB ready, SQLite ready, FAISS ready, `total_items=446`.
- Started n8n through the Windows CMD channel and verified ports `5678` and `5679`.
- Increased n8n watchdog startup wait from 90 seconds to 180 seconds.
- Installed the low-permission Startup fallback watchdog:
  - `C:\Users\pc\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ChengWorkspaceN8nWatchdog.cmd`
- Imported `docs/superpowers/specs/n8n-workflow-xiaobian-video.json` into n8n as an inactive draft:
  - workflow id: `xiaobianVideo001`
  - workflow name: `Xiaobian Short Video Automation`
- Started the single-entry main web gateway through `tools/enforce_single_entry_gateway.ps1`.
- Hardened the frontend shell contract:
  - `templates/chat.html` is the canonical source for `/chat_shell`.
  - `templates/chat_shell.html` is synced for the current runtime.
  - Future route mapping now points `/chat_shell` at `templates/chat.html`.
  - The task panel now defaults to unresolved work, escapes rendered task fields, sorts active work first, and shows an agent activity board.
  - Provider status polling now has slow-provider gaps and 429 backoff instead of hammering cloud endpoints.
- Hardened backend diagnosis and delegation:
  - Added image generation routing to Xiaobian with an OpenAI Images call when configured and a local SVG preview fallback.
  - Fused learner-style routing into the researcher agent so knowledge distillation and methodology work has one stronger owner.
  - Expanded research topic keyword coverage for startup, disability welfare, tenders, psychiatry, hematology, genetic diseases, linguistics, methodology, distillation, and philosophical suicide logic.
  - Added provider catalog/status metadata and disabled-cloud-provider reporting.
  - Added a controlled failed-task auto-retry cycle that creates linked retry tasks instead of silently losing failed work.
- Retargeted stale tests away from ignored `.sync_user_project` runtime artifacts and back to tracked canonical source files.
- Updated `tools/foundation_health_check.py` to verify the new frontend activity/backoff contract.
- Added `tools/chat_shell_browser_smoke.py` as a reusable headless Chrome/Edge gate for `/chat_shell`.
- Added browser smoke to the foundation checker with `auto|required|off` modes.
- Expanded `tests/tools/check_chat_shell_e2e.py` so HTTP smoke also checks the activity board and provider backoff contract.
- Added OpenClaw governance metadata in `core/openclaw_bridge.py`:
  - `health=governed_stopped` when the daemon is installed but intentionally not running.
  - `decision_state=prophet_decision_required` when starting or mutating OpenClaw needs governance approval.
  - `auto_start_allowed=false` so automation does not silently start system-layer services.
- Added OpenClaw status and governance rows to the frontend system monitor.
- Added `tools/n8n_workflow_preflight.py` as a reusable activation gate for the Xiaobian n8n workflow.
- Added n8n workflow preflight into `tools/foundation_health_check.py` inventory mode so blocked activation is visible without turning into a silent failure.

## Important Notes

- n8n took slightly longer than 120 seconds to expose port `5678`; this is why the watchdog default is now 180 seconds.
- The imported n8n workflow is inactive by design. The source spec now has timeout, cost controls, error policy, webhook header auth, and a controlled FFmpeg command. Live n8n still needs credentials, ffmpeg on PATH, and re-import of the hardened spec before activation.
- The main web process appears as a Python wrapper chain from `system_main.py` to `desktop_chat_app.py`; only the final process owns port `5001`.
- Scheduled Task registration was denied by Windows permissions, so the Startup folder fallback is the active persistence mechanism.
- The in-app Browser plugin still did not expose a JS evaluation tool, so visual validation now uses the local headless Chrome CDP smoke tool instead.
- `reports/foundation_health_latest.json` is generated evidence and remains ignored by git.
- `reports/chat_shell_browser_smoke_latest.json` and `reports/chat_shell_browser_smoke_latest.png` are generated evidence and remain ignored by git.
- `reports/n8n_workflow_preflight_latest.json` is generated evidence and remains ignored by git.

## Remaining Gaps

| Gap | Priority | Suggested Next Step |
|---|---|---|
| OpenClaw daemon is installed and governed-stopped | P1 | Start only after explicit prophet/governance approval; otherwise keep it as a visible non-running dependency. |
| n8n telemetry DNS messages still appear in logs | P2 | Identify the exact n8n 2.21 telemetry/feature-flag config keys before adding more env vars. |
| n8n workflow preflight is blocked | P1 | Clear provider credentials, n8n DB credentials, ffmpeg PATH, and re-import the hardened source spec before activation. |
| n8n workflow has no executions yet | P1 | Run a controlled manual test only after preflight reports `ready_for_activation`. |
| Obsidian root MOC still has local edits | P1 | Commit or intentionally separate vault UI/config edits from ProjectDocs content edits. |
| Working tree is intentionally dirty after this optimization pass | P1 | Review and commit the scoped infrastructure/frontend/backend/test changes separately from pre-existing report or bridge edits. |

## Link Targets

- [[ProjectDocs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK]]
- [[ProjectDocs/dev/N8N_AND_PROPHET_ENGINEER_STABILITY_REPORT_2026-05-28]]
- [[ProjectDocs/dev/SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25]]
- [[ProjectDocs/dev/OPENCLAW_INTEGRATION_AND_AGENT_ORG_STRENGTHENING_2026-05-30]]
