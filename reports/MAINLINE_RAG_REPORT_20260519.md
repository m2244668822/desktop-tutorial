# Mainline RAG Report

- generated_at: 2026-05-19T10:03:50
- workspace: `/Volumes/智能體/城城城程式`
- documents: `15`
- chunks: `314`
- ingestion_dir: `/Volumes/智能體/城城城程式/data/knowledge_hub/ingestion`

## Mainline Scope

This report indexes runtime-critical files only (entrypoints, core workflow, autonomy daemon, memory/knowledge bridge).

## Agent Coverage

- `工程師`: 2 files
- `研究員`: 4 files
- `總管`: 3 files
- `總管/申言者`: 6 files

## Top Retrieval Keywords

- `self`: 1183
- `str`: 851
- `get`: 734
- `return`: 577
- `def`: 350
- `dict`: 298
- `path`: 279
- `for`: 276
- `text`: 221
- `any`: 217
- `not`: 211
- `true`: 202
- `none`: 185
- `append`: 182
- `api`: 174
- `else`: 171
- `json`: 170
- `item`: 166
- `len`: 151
- `data`: 147
- `false`: 146
- `import`: 138
- `int`: 137
- `workspace`: 134
- `list`: 133
- `payload`: 128
- `datetime`: 120
- `name`: 119
- `except`: 117
- `and`: 117

## Indexed Files

- `core/backend_router.py` (總管/申言者, 2989 bytes)
- `core/command_layer.py` (總管/申言者, 3676 bytes)
- `core/langgraph_workflow.py` (總管/申言者, 20058 bytes)
- `core/memory_layers.py` (總管/申言者, 20841 bytes)
- `core/message_semantics.py` (總管/申言者, 10328 bytes)
- `core/workflow_runtime.py` (總管/申言者, 52031 bytes)
- `desktop_chat_app.py` (工程師, 166704 bytes)
- `system_main.py` (工程師, 5715 bytes)
- `tools/agent_autonomy_daemon.py` (總管, 9457 bytes)
- `tools/agent_memory_manager.py` (研究員, 28864 bytes)
- `tools/build_knowledge_ingestion.py` (研究員, 7699 bytes)
- `tools/enqueue_autonomy_task.py` (總管, 2076 bytes)
- `tools/local_memory_api.py` (研究員, 43032 bytes)
- `tools/manage_autopilot_daemon.sh` (總管, 2496 bytes)
- `tools/sync_knowledge_hub.py` (研究員, 4235 bytes)

## Findings

1. Mainline RAG can now target code-first runtime paths instead of only docs/reports.
2. Autonomy queue + workflow runtime are indexed together, enabling task-state retrieval and replay guidance.
3. Skill stability checks are runnable and indexable from the same knowledge hub context.

## Optimization Recommendations

1. Add reranker stage on top of `mainline_program_chunks.jsonl` for better long-query precision.
2. Add conflict policy fields inside every project skill to reduce routing ambiguity.
3. Expose autonomy state files as a lightweight backend endpoint for frontend live diagnostics.

## Compatibility Debug Update (2026-05-19)

- audit_report: `reports/portable_workspace_audit_20260519_full.json`
- health: `OK`
- required_files_missing: `0`
- required_dirs_missing: `0`
- skill_files_missing: `0`
- case_collisions: `0`
- hardcoded_path_hits: `183`

### Resolved In This Iteration

1. Fixed broken `data` link and re-pointed to local shared path: `data -> data_hdd_storage`.
2. Updated runtime scripts to avoid absolute macOS-only paths:
- `auto_pre_index.py`
- `fetch_academic_daily.py`
- `tools/system_health_check.py`
3. Mainline RAG ingestion now writes successfully to:
- `data/knowledge_hub/ingestion/mainline_program_documents.jsonl`
- `data/knowledge_hub/ingestion/mainline_program_chunks.jsonl`

### Remaining Cross-Platform Risk

1. Most remaining hardcoded paths are in `archive/`, `legacy/`, and historical reports.
2. These currently do not block mainline startup, autonomy loop, or RAG ingestion.
3. Next cleanup should prioritize executable scripts under `tools/` and root runtime files before touching docs/history.
