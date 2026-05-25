# Single Entry Gateway Policy (Windows/macOS Shared Workspace)

Date: 2026-05-25

## Goal

Stabilize frontend and agent execution by enforcing one canonical API entry:

- Canonical web/API entry: `http://127.0.0.1:5001`
- Frontend always calls port `5001`
- Backend handles aliases and prefix compatibility

## Routing Rules

- Accepted chat POST endpoints:
  - `/chat/agent`
  - `/chat/agent/`
  - `/api/send_message`
  - `/api/send_message/`
- Prefix compatibility:
  - `/Perob/*`
  - `/perob/*`
- Policy endpoint:
  - `GET /api/gateway/policy`

## Service Separation

- Main web service runs independently on `5001`
- n8n runs independently on `5678` via watchdog (not mixed into web startup)

## Operational Commands (Windows)

```powershell
# Enforce gateway + n8n watchdog
.\tools\enforce_single_entry_gateway.ps1

# Verify policy endpoint
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5001/api/gateway/policy
```

## Notes

- `tools/start_main_web_windows.ps1` stays responsible for main web only.
- `tools/n8n_watchdog_windows.ps1` stays responsible for n8n liveness.
- Keep frontend route logic thin; keep route compatibility in backend.
