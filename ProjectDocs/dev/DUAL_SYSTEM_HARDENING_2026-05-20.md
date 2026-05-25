# Dual System Hardening (2026-05-20)

## Scope
- Source workspace: `/Volumes/智能體/城城城程式`
- Microsoft-side handoff source: `docs/dev/DAILY_SYNC_2026-05-20_MAC_HANDOFF.md`
- Cross-platform baseline: `docs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md`

## What Was Read (Latest Microsoft-related Markdown)
1. `docs/dev/DAILY_SYNC_2026-05-20_MAC_HANDOFF.md`
2. `docs/dev/MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md`
3. `reports/MAIN_PROGRAM_FRONTEND_BACKEND_LOGIC_REVIEW_20260519.md`

## Key Findings
1. Windows side already has runtime completion for Node+n8n, but path shadow can happen (multiple `node.exe` candidates).
2. Git metadata corruption remains the highest operational risk and can block clean deploy/push workflows.
3. Data root compatibility is mostly solved by `data` -> `data_hdd_storage` fallback logic.
4. OCI SSH is scriptable, but should be included in standardized bootstrap checklist.

## Implemented Hardening
1. Updated `tools/windows_bootstrap.ps1`:
   - Added `-RunHarmonyCheck` switch.
   - Detects multiple `node` candidates and prints potential shadow risk.
   - Resolves and prints preferred WinGet `n8n.cmd` path.
   - Optional one-shot output to `reports/harmony_check_windows_latest.json`.
2. No breaking changes to existing startup commands.

## Recommended Unified Flow (Mac + Windows)
1. Bootstrap / verify environment:
   - macOS:
     - `python3 system_main.py health`
     - `python3 tools/harmony_check.py --json-out reports/harmony_check_mac_latest.json`
   - Windows:
     - `.\tools\windows_bootstrap.ps1 -Workspace . -RunHarmonyCheck`
2. Verify shared data root:
   - check `data` and `data_hdd_storage` availability
   - if junction/symlink unavailable, confirm runtime fallback still points to `data_hdd_storage`
3. Verify LLM and workflow CNS:
   - `/api/providers/status`
   - `/api/frontend/snapshot`
   - `/api/knowledge/status`
4. Verify OCI access on Windows:
   - `.\tools\configure_oci_ssh_windows.ps1 -HostName <OCI_PUBLIC_IP> -TestConnection -Force`
5. Resolve Git integrity before high-risk operations:
   - if `metadata_corrupt`, re-clone fresh repo and move working files (do not move broken `.git`)

## Command Reference
```powershell
.\tools\windows_bootstrap.ps1 -Workspace . -InstallEditorExtensions -RunHarmonyCheck
.\.venv\Scripts\python.exe system_main.py web --host 127.0.0.1 --port 5001
```

```bash
python3 tools/portable_workspace_audit.py --workspace . --json-out reports/portable_workspace_audit_latest.json
python3 tools/harmony_check.py --json-out reports/harmony_check_mac_latest.json
```

## Acceptance Checklist
- [ ] `system_main.py health` passes on both systems
- [ ] `harmony_check` outputs generated on both systems
- [ ] web entrypoint reachable: `/chat_shell`
- [ ] knowledge hub reachable: `/api/knowledge/status`
- [ ] OCI alias login works on Windows: `ssh oci-agent`
- [ ] Git repository healthy or migrated to fresh clone
