# Data Tracking Tiers

Last updated: 2026-04-30

Purpose: keep Git tracking rules clear across runtime artifacts, semi-state
outputs, and core state data.

## Tier 1: runtime (do not track)

- `logs/`
- `reports/observability/`

Policy:

- Runtime artifacts are not tracked in Git.
- Keep local files for debugging and operations.
- If any file under these paths appears in staged/tracked changes again,
  remove it from index with `git rm --cached`.

## Tier 2: semi-state (observe first)

- `reports/workflow_runs/`
- `logs/workflow_runs/`

Policy:

- Treat as operational history and inspect usefulness before deciding long-term
  retention strategy.
- Default stance is "observe, do not aggressively clean".
- Avoid mixing these files with source-code commits.

## Tier 3: state (do not remove now)

- Memory data
- Conversation data
- Learning data

Typical paths:

- `500/llama32-chat/data/`
- `data/knowledge_hub/memory_layers/`
- `data_hdd_storage/`

Policy:

- These are core state assets and are not part of this cleanup phase.
- Do not batch-untrack or remove without explicit migration/backup plan.

## Current decision snapshot

- Runtime artifacts exited Git tracking.
- Local runtime files are preserved.
- Core state data remains untouched.
