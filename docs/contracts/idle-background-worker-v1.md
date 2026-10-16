# Idle Background Worker v1

The worker is a separate local process. It does not own the foreground chat
conversation, Inbox executor, FilmCraft project, or canonical promotion path.

## Start

One pass:

```powershell
$env:VAULT_WORKSPACE_ROOT = "C:\path\to\vault"
$env:NVIDIA_API_KEY = "nvapi-..."
py -3 tools/run_idle_embedding_worker.py
```

Continuous idle polling:

```powershell
$env:WHITE_STUDIO_IDLE_POLL_SECONDS = "30"
py -3 tools/run_idle_embedding_worker.py --loop
```

The process polls every 30 seconds, but the policy requires five minutes of
user inactivity before background work is allowed. A queued or running
foreground task always pauses the worker.

## Outputs

All outputs are derived runtime state under
`runtime/.mcp-state/embedding-index/`:

- `embedding-index.jsonl`: source-hashed passage vectors
- `checkpoint.json`: resumable cursor and operation identity
- `orchestrator/`: durable task and event projections
- `provenance.json`: source commit, manifest hash, model, and dimension
- `validation.json`: candidate validation result
- `canonical-index-proposal.json`: promotion proposal

The worker never edits formal canonical Markdown or applies canonical
promotion. A promotion must be reviewed separately.

## Preemption and failure

- Foreground task: checkpoint and pause.
- User activity: policy pause.
- CPU at or above 80%: policy pause.
- Memory at or above 85%: policy pause.
- API failure, timeout, 401, or 429: checkpoint and block/defer.
- Missing or invalid vectors: block. No partial success is reported.
- Existing `source_path + sha256 + model_id`: skip as duplicate.

Nemotron-3-Embed-1B uses `passage` for indexing and `query` for retrieval.
It is not a chat or tool-calling model.
