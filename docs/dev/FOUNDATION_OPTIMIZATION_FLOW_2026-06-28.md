# Foundation Optimization Flow - 2026-06-28

## Purpose

This document is the current operating flow for keeping the workspace maintainable instead of letting fixes pile into unstable code. It defines the architecture boundary, the evidence gates, and the order of work for frontend, backend, data, n8n, Git, and handoff.

## Current Architecture Boundary

| Layer | Responsibility | Primary Evidence |
|---|---|---|
| Single web gateway | User-facing web/API entry on `127.0.0.1:5001` | `/status`, `/api/get_status`, `/api/gateway/policy` |
| Frontend shell | Canonical chat UI in `templates/chat.html`; synced runtime copy in `templates/chat_shell.html` | frontend contract tests, browser smoke, `/chat_shell` |
| Backend core | Routing, agent status, memory, task board, workflow runtime | unit tests, `py_compile`, gateway API status |
| Automation | n8n editor and task broker on `5678/5679` | n8n health endpoints, SQLite workflow inventory, workflow preflight |
| Data and memory | Knowledge Hub manifest, SQLite, FAISS, conversation sources | `data/knowledge_hub/manifest.json`, sync scripts |
| Governance | OpenClaw and high-impact automation state | `/api/get_status`, `openclaw_runtime`, local gateway health |
| Git and handoff | Branch, staged scope, cross-machine continuation | `git status -sb`, handoff docs, health reports |

## Non-Negotiable Rules

1. The frontend must not be treated as healthy from static inspection alone. Use browser smoke for real DOM, console, runtime exception, and layout checks.
2. Runtime reports under `reports/` are evidence, not source of truth. Commit tools, tests, specs, and docs; do not commit generated evidence unless explicitly archiving a snapshot.
3. n8n workflows stay inactive until `tools/n8n_workflow_preflight.py` reports `ready_for_activation`.
4. OpenClaw local execution must be observable through `openclaw_runtime`; starting or mutating OpenClaw still requires explicit governance approval.
5. Every infrastructure change needs one of: a test, a health-check signal, or a runbook update. Prefer all three for shared behavior.
6. Do not solve drift by adding another parallel entrypoint. Either strengthen the existing entrypoint or clearly retire the old path.

## Phase 0: Freeze And Snapshot

Before changing files:

```powershell
git status -sb
git log -5 --oneline --decorate
```

Confirm the real workspace path. On the current Windows machine the authoritative repo is:

```text
E:\智能體\城城城程式
```

If a shell, Codex session, or Mac terminal points at another path such as `F:\城城城程式`, `/Volumes/...`, or a stale symlink, treat that as a workspace context problem before debugging the app.

## Phase 1: Runtime Baseline

Start or verify the runtime services:

```powershell
powershell -ExecutionPolicy Bypass -File tools\enforce_single_entry_gateway.ps1
python tools\foundation_health_check.py --browser-smoke auto
```

Strict local validation:

```powershell
python tools\foundation_health_check.py --browser-smoke required
```

Expected checks:

| Check | Meaning |
|---|---|
| `workspace_context` | cwd, git root, and required repo files are coherent |
| `ports` | `5001`, `5678`, `5679`, and `11434` are listening when full runtime is expected |
| `gateway` | frontend/backend gateway status APIs respond |
| `openclaw_runtime` | OpenClaw CLI and local gateway health prove local execution support |
| `n8n` | n8n health endpoints and SQLite inventory are readable |
| `n8n_workflow_preflight` | workflow activation state is visible |
| `knowledge_hub` | data manifest and indexes are usable |
| `frontend_static_contract` | canonical chat shell tokens have not drifted |
| `browser_smoke` | real browser load has no visible/runtime/console breakage |

The JSON report also includes `next_actions`. These are sorted repair steps with:

| Field | Use |
|---|---|
| `source` | Which health check produced the action |
| `priority` | `P0` to `P3` repair priority |
| `summary` | Human-readable action |
| `windows` / `macos` | Platform-specific commands or UI steps |
| `verify` | The command or condition that proves the action worked |
| `evidence` | Raw details that caused the action |

The terminal prints the first actions directly, and the full set stays in the JSON report.

The report separates execution health from remaining work:

| Field | Meaning |
|---|---|
| `ok` | Every health check completed within its current policy |
| `attention_required` | At least one `next_actions` item remains |
| `action_summary.blocking_attention` | A `P0` or `P1` action still needs attention |

This matters because n8n preflight can be operationally visible while still `blocked_for_activation`.

## Phase 2: Frontend Reliability

The canonical frontend source is `templates/chat.html`. Keep `templates/chat_shell.html` synced when runtime compatibility needs the copy.

Required gates:

```powershell
python -m pytest tests\test_frontend_sync_contract.py tests\test_chat_frontend_api_cleanup.py tests\test_desktop_web_compat_routes.py --tb=short
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 390 --height 844
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 768 --height 1024
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 1440 --height 1000
```

The mobile contract is part of the foundation check. Removing the narrow viewport CSS must fail the static contract before it becomes a runtime surprise.

## Phase 3: Backend Diagnosis From Multiple Angles

Backend status is not a single signal. Inspect it from several directions:

| Direction | Evidence |
|---|---|
| API behavior | `/status`, `/api/get_status`, `/api/gateway/policy` |
| Process and ports | `foundation_health_check.py`, PowerShell port checks |
| Code importability | `python -m py_compile ...` |
| Data state | Knowledge Hub manifest, n8n SQLite counts |
| Governance state | OpenClaw local execution, gateway health, and `decision_state` |
| Task continuity | task board retry and unresolved-task views |

Minimum backend gate:

```powershell
python -m py_compile desktop_chat_app.py core\web_server.py core\knowledge_hub.py core\workflow_runtime.py tools\foundation_health_check.py tools\n8n_workflow_preflight.py
python -m pytest tests\test_foundation_health_check.py tests\test_openclaw_bridge.py tests\test_n8n_workflow_preflight.py --tb=short
```

## Phase 4: Data And Memory Governance

`data/knowledge_hub/manifest.json` is the cross-machine handoff card for memory state. Regenerate it after moving between Windows and macOS:

```powershell
python tools\sync_knowledge_hub.py
```

If paths inside the manifest point to an old machine, do not patch them by hand. Rerun the sync script from the real repo root.

## Phase 5: n8n Production Hardening

Run the preflight before activating any workflow:

```powershell
python tools\n8n_workflow_preflight.py
```

Inventory mode is allowed during development:

```powershell
python tools\n8n_workflow_preflight.py --allow-blockers
```

The preflight JSON report includes:

| Field | Use |
|---|---|
| `issues` | Raw blockers and warnings with evidence |
| `remediation_plan` | Deduplicated Windows/macOS repair steps for each recurring blocker |
| `activation_sequence` | Ordered checklist that must be completed before unattended automation |
| `db.workflow_contract` | Live imported workflow contract for stale-import detection |

Known activation blockers:

| Blocker | Required Action |
|---|---|
| provider credentials | Configure Gemini/OpenAI credentials in n8n |
| n8n DB credentials | Ensure `credentials_entity` is non-empty |
| FFmpeg | Install FFmpeg and confirm it is on PATH |
| stale imported workflow | Re-import the hardened source spec |
| zero executions | Run a controlled manual test only after preflight is ready |

## Phase 6: Anti-Sprawl Review

Before committing:

1. Check whether the change strengthens an existing gate instead of adding a parallel path.
2. Confirm generated reports are ignored unless intentionally archived.
3. Confirm every new behavior has a named owner file and a test or health-check signal.
4. Confirm Mac/Windows path assumptions are documented when they matter.
5. Confirm the final `git diff --stat` matches the intended scope.

## Commit Gate

Recommended focused gate:

```powershell
python -m pytest tests\test_foundation_health_check.py tests\test_frontend_sync_contract.py tests\test_n8n_workflow_preflight.py --tb=short
python -m py_compile tools\foundation_health_check.py tools\chat_shell_browser_smoke.py tools\n8n_workflow_preflight.py
```

Full gate when runtime services are up:

```powershell
python tools\foundation_health_check.py --browser-smoke required
python -m pytest tests --tb=short
```

## Remaining Work

| Gap | Priority | Next Action |
|---|---|---|
| n8n activation blocked | P1 | Add credentials, FFmpeg, re-import hardened workflow, rerun preflight |
| Mac runtime not reverified after latest Git handoff | P1 | Pull branch on Mac and run foundation health with browser smoke |
| Obsidian vault state may differ from ProjectDocs | P2 | Audit vault-only edits separately from tracked docs |
| Runtime services may be stopped between shifts | P2 | Treat port failures as startup state unless reproducible after launcher |
