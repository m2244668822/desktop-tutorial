# Cross-System Linkage and Doc Consolidation (2026-05-26)

## Scope

This document consolidates older sync/integrity notes and records why the knowledge graph looked fragmented.

Graph observation scope used in this round:

- `docs/dev/*.md`
- Obsidian Vault with `ProjectDocs` junction to the workspace `docs/` directory

## What We Observed

### 1) `docs/dev` was fully disconnected

- Total docs: `14`
- Orphan docs: `14`
- Meaning: every file had `in=0, out=0`

This means the files existed, but they did not reference each other, so the graph had no strong backbone.

### 2) Obsidian graph had a visible hub but many side islands

- Total docs detected in vault graph scope: `75`
- Orphans: `50`

Most links were concentrated around MOC/dashboard notes, while many project docs stayed isolated.

## Why Linkage Was Low (Practical Reasons)

1. Same topic split across many date-stamped files, but no explicit cross-links.
2. Old handoff docs overlapped in content (Git integrity, dual-system sync, startup channels), creating parallel notes instead of one canonical note.
3. Some legacy docs contained encoding/typo noise, which reduced readability and reuse.
4. Operational updates were stored as reports, but not linked back into long-lived runbooks.

## Consolidation Decision

Merged and retired these legacy files:

1. `DAILY_SYNC_2026-05-20_MAC_HANDOFF.md`
2. `DUAL_SYSTEM_HARDENING_2026-05-20.md`
3. `SYNC_CHANNEL_TAGS_2026-05-22.md`
4. `GIT_INTEGRITY_AND_BRANCH_TRACKING_2026-05-22.md`
5. `WORK_STATUS_INTEGRITY_DUAL_SYSTEM_2026-05-22.md`

## Consolidated Content (from the retired files)

### A. Git Integrity Summary

- `empty object = 0` is not corruption; it means empty broken objects were already cleared.
- Healthy baseline checks:
  - `git fsck --full --no-reflogs`
  - `git count-objects -vH`
  - `git branch -vv`
- Branch tracking should include all needed `origin/*` branches.

### B. Cross-System Runtime Baseline

- Canonical web/API entry: `127.0.0.1:5001`
- n8n stays independent and long-running (`5678`), not mixed into web startup script.
- Windows n8n startup should use CMD channel:
  - `.\tools\start_n8n_windows.cmd`
  - or `cmd /c n8n`

### C. Sync Channels

- macOS sync channel:
  - script: `tools/sync_ssd_to_hdd.sh`
  - tag: `mac-sync`
- Windows sync channel:
  - script: `tools/sync_workspace_windows.ps1`
  - tag: `windows-sync`

### D. Daily Cross-Platform Checklist

1. Run health:
   - `system_main.py health`
2. Run harmony check:
   - `tools/harmony_check.py`
3. Verify web entry:
   - `/status`
   - `/chat_shell`
4. Verify knowledge layer:
   - `ChatGPT DB / SQLite / FAISS` readiness
5. Verify Git integrity before major push/merge operations.

## Linkage Improvement Rules (Keep the Graph Strong)

1. Every new MD must include at least 3 links:
   - 1 to a MOC or dashboard
   - 1 to a technical policy/runbook
   - 1 to a report or task outcome
2. Keep one canonical doc per recurring theme; append updates instead of creating parallel clones.
3. Keep startup policy and sync policy linked both ways.
4. Maintain UTF-8 plain text in runbooks to avoid mojibake drift.

## Active Docs Map (Current)

- [MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md](./MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md)
- [SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25.md](./SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25.md)
- [NOTEBOOKLM_ARCH_PORT_BRANCH_REPORT_2026-05-25.md](./NOTEBOOKLM_ARCH_PORT_BRANCH_REPORT_2026-05-25.md)
- [MAIN_PROGRAM_PROGRESS_TASK_AUDIT_AND_P0_CLASSIFICATION_2026-05-26.md](./MAIN_PROGRAM_PROGRESS_TASK_AUDIT_AND_P0_CLASSIFICATION_2026-05-26.md)
- [AGENT_RELATIONSHIP_ENHANCEMENT_PLAYBOOK_2026-05-25.md](./AGENT_RELATIONSHIP_ENHANCEMENT_PLAYBOOK_2026-05-25.md)
- [AGENT_REPLY_OPTIMIZATION_VERIFICATION_2026-05-25.md](./AGENT_REPLY_OPTIMIZATION_VERIFICATION_2026-05-25.md)
- [LLM_DEFAULT_FALLBACK_FIX_2026-05-25.md](./LLM_DEFAULT_FALLBACK_FIX_2026-05-25.md)
- [GITHUB_BRANCH_PROTECTION_CHECKLIST.md](./GITHUB_BRANCH_PROTECTION_CHECKLIST.md)
- [GIT_AUTONOMY_SKILL_GUIDE.md](./GIT_AUTONOMY_SKILL_GUIDE.md)
- [SSD_TO_HDD_MIGRATION_AND_LAYOUT_REMEDIATION_20260517.md](./SSD_TO_HDD_MIGRATION_AND_LAYOUT_REMEDIATION_20260517.md)

## Deprecation Record

Retired file names are preserved in this section for traceability and Git history lookup:

- `DAILY_SYNC_2026-05-20_MAC_HANDOFF.md`
- `DUAL_SYSTEM_HARDENING_2026-05-20.md`
- `SYNC_CHANNEL_TAGS_2026-05-22.md`
- `GIT_INTEGRITY_AND_BRANCH_TRACKING_2026-05-22.md`
- `WORK_STATUS_INTEGRITY_DUAL_SYSTEM_2026-05-22.md`

## Task Status Snapshot (2026-05-26)
- Status: `completed-core`
- Completed:
  - Legacy duplicated sync docs consolidated and deprecation recorded.
  - Linkage rules established for non-fragmented graph growth.
- Pending:
  - Quarterly cleanup for newly created duplicate docs.

