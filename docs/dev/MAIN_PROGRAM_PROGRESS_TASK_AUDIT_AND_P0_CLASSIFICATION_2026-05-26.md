# Main Program Progress, Task Audit, and P0 Classification (2026-05-26)

## Live Status Snapshot (verified on 2026-05-26)

- `GET /status`: `ok=true`
- `GET /api/gateway/policy`: `HTTP 200`
- `GET /api/diag`: `bridge_ready=true`, `monitor_active=true`
- Ports listening:
  - `5001` main web
  - `5678` n8n
  - `5679` n8n task broker
  - `11434` Ollama
- Knowledge layer:
  - `total_items=446`
  - `sqlite_ready=true`
  - `faiss_ready=true`
  - `chatgpt_database_ready=true`

## Historical MD Task Audit

1. Completed core
- `MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md`
- `SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25.md`
- `LLM_DEFAULT_FALLBACK_FIX_2026-05-25.md`
- `CROSS_SYSTEM_LINKAGE_AND_DOC_CONSOLIDATION_2026-05-26.md`

2. In-progress follow-up
- `AGENT_REPLY_OPTIMIZATION_VERIFICATION_2026-05-25.md`
  - Pending: training overlay branch merge and post-merge regression check.
- `AGENT_RELATIONSHIP_ENHANCEMENT_PLAYBOOK_2026-05-25.md`
  - Pending: weekly KPI-based quality tracking and drift guard tuning.

3. Deprecated and removed from active flow
- `DAILY_SYNC_2026-05-20_MAC_HANDOFF.md`
- `DUAL_SYSTEM_HARDENING_2026-05-20.md`
- `SYNC_CHANNEL_TAGS_2026-05-22.md`
- `GIT_INTEGRITY_AND_BRANCH_TRACKING_2026-05-22.md`
- `WORK_STATUS_INTEGRITY_DUAL_SYSTEM_2026-05-22.md`

## P0 Document Classification (Highest Priority)

### P0-A: Runtime and Recovery (must-have)
1. [MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md](./MAC_WINDOWS_SHARED_WORKSPACE_RUNBOOK.md)
2. [SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25.md](./SINGLE_ENTRY_GATEWAY_POLICY_2026-05-25.md)
3. [LLM_DEFAULT_FALLBACK_FIX_2026-05-25.md](./LLM_DEFAULT_FALLBACK_FIX_2026-05-25.md)
4. [MAIN_PROGRAM_PROGRESS_TASK_AUDIT_AND_P0_CLASSIFICATION_2026-05-26.md](./MAIN_PROGRAM_PROGRESS_TASK_AUDIT_AND_P0_CLASSIFICATION_2026-05-26.md)

### P0-B: Agent Quality and Memory (must-have)
1. [AGENT_REPLY_OPTIMIZATION_VERIFICATION_2026-05-25.md](./AGENT_REPLY_OPTIMIZATION_VERIFICATION_2026-05-25.md)
2. [AGENT_RELATIONSHIP_ENHANCEMENT_PLAYBOOK_2026-05-25.md](./AGENT_RELATIONSHIP_ENHANCEMENT_PLAYBOOK_2026-05-25.md)
3. [NOTEBOOKLM_ARCH_PORT_BRANCH_REPORT_2026-05-25.md](./NOTEBOOKLM_ARCH_PORT_BRANCH_REPORT_2026-05-25.md)

### P1: Governance and audit support
1. [CROSS_SYSTEM_LINKAGE_AND_DOC_CONSOLIDATION_2026-05-26.md](./CROSS_SYSTEM_LINKAGE_AND_DOC_CONSOLIDATION_2026-05-26.md)
2. [GITHUB_BRANCH_PROTECTION_CHECKLIST.md](./GITHUB_BRANCH_PROTECTION_CHECKLIST.md)
3. [GIT_AUTONOMY_SKILL_GUIDE.md](./GIT_AUTONOMY_SKILL_GUIDE.md)

## Cleanup and Conflict-Avoidance Actions

1. Kept only one active consolidation source for legacy sync/integrity docs.
2. Replaced ambiguous triage file naming in Vault:
   - old placeholder note replaced by `10_待判定收件匣_2026-05-26.md`
3. Added explicit status snapshots to core runbooks so completed vs pending items are visible.

## Next Optimization Cycle

1. Merge `training-overlay` changes into active governance branch with controlled regression.
2. Add weekly KPI report for response diversity and drift.
3. Run doc dedupe scan monthly to prevent fragmented runbooks from returning.
