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
| gateway | OK | `gateway: ready` |
| OpenClaw runtime | OK | `openclaw_runtime: ready`, `local_execution.supported=true` |
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

## OpenClaw Local Execution

OpenClaw is locally executable on this Windows machine:

| Criterion | Result |
|---|---|
| CLI installed | PASS |
| version | `OpenClaw 2026.5.27 (27ae826)` |
| local gateway listener | PASS, `127.0.0.1:18789` |
| health endpoint | PASS, `http://127.0.0.1:18789/healthz` returned `{"ok":true,"status":"live"}` |
| foundation check | PASS, `openclaw_runtime: ready` |

The scheduled task can report `Ready` while the local gateway is live through `%USERPROFILE%\.openclaw\gateway.cmd`; the bridge now records that as `task_not_running_but_gateway_live` rather than incorrectly reporting OpenClaw as stopped.

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
| FFmpeg unavailable | P1 | Install FFmpeg and verify `ffmpeg -version`, or set `FFMPEG_PATH` / `XIAOBIAN_FFMPEG_PATH` before starting n8n |
| live workflow stale | P1 | Re-import `docs/superpowers/specs/n8n-workflow-xiaobian-video.json` so FFmpeg path override support reaches n8n DB |
| OpenClaw mutation governance | P1 | Keep `prophet_required_for_mutation=true`; do not auto-mutate |

## Interpretation

The runtime is operational for gateway, frontend, OpenClaw local execution, n8n visibility, Knowledge Hub, and browser smoke. It is not production-ready for Xiaobian n8n workflow activation until the preflight blockers are cleared.

## 2026-07-08 Runtime Controller Recheck

The runtime was restarted through the controlled service entrypoint:

```powershell
python tools\runtime_service_controller.py start --components web,n8n,ollama --wait-seconds 180
python tools\runtime_service_controller.py start --components openclaw --allow-openclaw-mutation --wait-seconds 90
python tools\runtime_service_controller.py status --json-out reports\runtime_service_controller_health_status.json
```

The controller now requires both listening ports and HTTP health URLs before reporting a service as ready. This prevents a false ready state where OpenClaw listens on `18789` but `/healthz` is still not responsive.

| Service | Result |
|---|---|
| web | ready, `5001`, `/status` OK |
| n8n | ready, `5678/5679`, both `/healthz` endpoints OK |
| Ollama | ready, `11434`, `/api/tags` OK |
| OpenClaw | ready, `18789`, `/healthz` OK |

Follow-up verification:

```powershell
python tools\runtime_dependency_doctor.py --allow-missing --json-out reports\runtime_dependency_doctor_after_mobile_fix.json
python tools\foundation_health_check.py --browser-smoke required --json-out reports\foundation_health_after_mobile_fix.json
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 390 --height 844
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 768 --height 1024
python tools\chat_shell_browser_smoke.py --base-url http://127.0.0.1:5001 --width 1440 --height 1000
```

Results:

| Check | Result |
|---|---|
| `runtime_dependency_doctor` | attention required only for FFmpeg; OpenClaw local execution ready |
| `foundation_health_check --browser-smoke required` | all runtime/frontend checks ready; attention remains for FFmpeg and n8n activation |
| mobile browser smoke `390x844` | ready after text-integrity contract fix |
| tablet browser smoke `768x1024` | ready |
| desktop browser smoke `1440x1000` | ready |

Mobile note: the first 390px run failed because the browser smoke required OpenClaw monitor copy in visible `innerText`, while the mobile layout intentionally hides the right monitor panel. The smoke gate now audits required copy through DOM `textContent` while still checking the full DOM for mojibake, replacement characters, and private-use codepoints.

## 2026-07-08 FFmpeg And n8n Import Recheck

FFmpeg was installed with winget and the hardened workflow spec was re-imported into the live n8n database:

```powershell
winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements
cmd /c n8n import:workflow --input docs\superpowers\specs\n8n-workflow-xiaobian-video.json
python tools\runtime_service_controller.py start --components n8n --wait-seconds 180
```

The current shell still could not resolve `ffmpeg` through PATH immediately after install, so the repo now uses `tools/runtime_binary_locator.py` as a shared resolver. It finds the winget package path and lets preflight, dependency doctor, and the n8n controller agree on the same FFmpeg binary.

Current evidence:

| Check | Result |
|---|---|
| `runtime_dependency_doctor` | ready; FFmpeg, OpenClaw, n8n, Ollama, Python, and Node all OK |
| `n8n_workflow_preflight` | blocked only by credentials; `credential_setup_plan` groups the manual n8n work by provider |
| `foundation_health_check --browser-smoke required` | runtime/frontend/OpenClaw ready; attention remains for n8n credentials |

Remaining activation blockers:

| Blocker | Reason |
|---|---|
| Gemini Parser credentials | requires real Gemini credential binding in n8n |
| DALL-E 3 Generator credentials | requires real OpenAI credential binding in n8n |
| OpenAI TTS credentials | requires real OpenAI credential binding in n8n |
| n8n credential DB empty | requires at least one real provider credential |

Credential setup details now appear in the preflight JSON:

| Provider | Credential Type Guidance | Nodes |
|---|---|---|
| OpenAI | installed n8n credential type `openAiApi`; required field `apiKey` | DALL-E 3 Generator, OpenAI TTS |
| Google Gemini | exact Gemini credential file was not present in the installed n8n-nodes-base package; use UI/provider candidates from `credential_setup_plan` | Gemini Parser |

No API keys or placeholder secrets are stored in the repo. Create credentials in each machine's n8n credential store, bind the listed nodes, then rerun:

```powershell
python tools\n8n_workflow_preflight.py --allow-blockers
python tools\foundation_health_check.py --browser-smoke required
```

The preflight now reports `workflow.credential_binding_source` and `credential_setup_plan.binding_source`. When the workflow exists in the local n8n DB, credential binding is checked against `n8n_database_workflow` nodes and `credentials_entity` metadata by id/name/type. It does not read `credentials_entity.data`.

## 2026-07-09 Goal Audit Gate

The foundation health check now includes `runtime_service_controller` as its own gate, so service readiness is proven through the controlled entrypoint as well as direct port/API checks.

The health report also includes `repo_secret_hygiene`, which scans tracked text files for obvious provider keys and verifies that `.gitignore` protects runtime and secret artifacts. This keeps the n8n credential fix pointed at the n8n credential store rather than Git.

Current completion audit command:

```powershell
python tools\foundation_health_check.py --browser-smoke required --json-out reports\foundation_health_goal_audit_current.json
python tools\foundation_goal_audit.py --health-report reports\foundation_health_goal_audit_current.json --json-out reports\foundation_goal_audit_current.json --allow-incomplete
```

Expected status before real n8n credentials are added:

| Requirement | Status |
|---|---|
| foundation architecture ready | passed |
| frontend issue-free gate | passed |
| backend multi-angle detection | passed |
| repo secret hygiene | passed when no tracked API keys are found |
| OpenClaw local execution ready | passed |
| n8n activation ready | blocked until real provider credentials are created and bound |

During source edits, the optimization flow requirement may also report incomplete because Git has uncommitted source changes. After committing source changes, only generated report files should remain dirty.

## 2026-07-14 Browser Smoke Matrix Gate

`foundation_health_check.py --browser-smoke required` now runs the chat shell browser smoke as a viewport matrix instead of a single desktop-sized run:

| Viewport | Size |
|---|---|
| mobile | `390x844` |
| tablet | `768x1024` |
| desktop | `1440x1000` |

`foundation_goal_audit.py` also requires all three viewport results before `frontend_issue_free` can pass. A single desktop smoke result is no longer enough to support the "frontend issue-free" completion claim.

## 2026-07-14 n8n Manual Execution Evidence Gate

`n8n_workflow_preflight.py` now separates "blockers are cleared" from "safe to activate unattended automation":

| Status | Meaning |
|---|---|
| `blocked_for_activation` | Credential, workflow, dependency, or safety blockers remain |
| `ready_for_manual_execution` | Preflight blockers are clear, but no successful controlled manual execution is recorded yet |
| `ready_for_activation` | Preflight blockers are clear and at least one successful manual execution exists in n8n execution metadata |

The new `manual_execution_plan` reads only `execution_entity` metadata from the local n8n SQLite database: workflow id, finished state, mode, status, and timestamps. It does not read `execution_data`, node payloads, API keys, generated text, media, or secret material.

Current activation interpretation:

| Gate | Result |
|---|---|
| provider credentials | still require real Gemini/OpenAI credential binding on each machine |
| manual execution evidence | required after credentials are bound and before unattended activation |
| goal audit | remains incomplete until `n8n_activation_ready` sees preflight `ready_for_activation` |

## 2026-07-14 Backend Diagnostic Matrix Gate

`foundation_health_check.py` now writes a top-level `diagnostic_matrix` alongside raw `checks` and `next_actions`. The matrix groups existing checks by ownership layer so backend issues can be decomposed before code changes begin:

| Group | Current Use |
|---|---|
| `workspace_shell` | separate stale cwd, Git root, and shell path problems from app bugs |
| `runtime_dependencies` | show dependency/PATH/compile failures together |
| `service_control` | separate controller and port readiness from API failures |
| `gateway_backend` | isolate web gateway/API behavior |
| `openclaw_governance` | keep local execution support and governed mutation visible |
| `automation_n8n` | keep n8n service health separate from activation blockers |
| `data_memory` | isolate Knowledge Hub/data manifest state |
| `frontend_runtime` | keep browser/static frontend gates grouped |
| `repo_hygiene` | keep secret hygiene and dirty worktree scope separate |

`foundation_goal_audit.py` includes backend-related matrix rows in the `backend_multi_angle_detection` evidence. This prevents a single green/bad label from hiding which layer actually owns the next repair.
