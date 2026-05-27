# Data Layer Source of Truth

Last updated: 2026-04-30

This file defines the current data-layer authority to avoid path confusion.
Tracking policy tiers are documented in `docs/DATA_TRACKING_TIERS.md`.

## 1) Canonical data roots

- `data/`
  - Runtime hot-data entrypoint.
  - In this workspace, `data` is a symlink to external fast storage.
  - Treat this as a mutable runtime area.

- `data_hdd_storage/`
  - Local cold-data mirror and historical logs.
  - Used as fallback/reference when fast storage is unavailable.

- `500/llama32-chat/data/`
  - Llama subsystem structured data (conversation core, local knowledge, diagnostics).
  - Primary source for `LocalMemoryAPI` and learning pipeline inputs.

- `.sync_user_project/instance/chat_history.db`
  - Runtime chat DB for sync/user project surface.
  - Mutable runtime DB, not source code.

## 2) Data authority by use-case

- Conversation primary: `500/llama32-chat/data/conversations.json`
- Large imported knowledge DB: `500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json`
- Knowledge hub manifest: `data/knowledge_hub/manifest.json`
- Memory index (FAISS + SQLite): `data/knowledge_hub/memory_layers/`
- Runtime workflow/observability logs: `logs/`, `reports/observability/`, `reports/workflow_runs/`

## 3) What caused confusion

- Three roots are active at the same time: `data/`, `data_hdd_storage/`, `500/llama32-chat/data/`.
- `data/` is a symlink, so Git/path behavior differs from normal directories.
- Generated runtime artifacts and imported data were mixed into tracked paths.

## 4) Guardrails now in place

- `.gitignore` now blocks newly generated runtime/data artifacts under:
  - `data/`, `data_hdd_storage/`, `.sync_user_project/`, `logs/`
  - `reports/observability/`, `reports/workflow_runs/`, `reports/evals/`
  - `500/llama32-chat/data/`, `500/llama32-chat/logs/`, `500/llama32-chat/sessions/`
- `tools/local_memory_api.py` now auto-selects latest conversation/daily files and supports fallback roots.
- `core/workflow_runtime.py` storage health check now uses workspace-based HDD path instead of hard-coded absolute path.

## 5) Daily sanity checks

```bash
# 1) Rebuild and verify knowledge hub manifest
.venv/bin/python tools/sync_knowledge_hub.py
.venv/bin/python -m json.tool data/knowledge_hub/manifest.json >/dev/null

# 2) Quick data-layer health
.venv/bin/python - <<'PY'
from tools.local_memory_api import LocalMemoryAPI
api = LocalMemoryAPI(base_dir='.')
print('sources:', len(api.memory_sources))
for key in ['conversation_logs', 'daily_routine', 'knowledge_hub_manifest']:
    p = api.memory_sources[key]
    print(key, '=>', p, 'exists=', p.exists())
PY
```

## 6) Important note about existing tracked data

`.gitignore` only affects untracked files.

If old data artifacts are already tracked in Git index, they will still appear in `git status` until explicitly untracked from index (`git rm --cached ...`).
