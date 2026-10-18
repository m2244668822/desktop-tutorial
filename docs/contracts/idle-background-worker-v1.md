# Idle Background Worker v1

The worker is a separate local process. It does not own the foreground chat
conversation, Inbox executor, FilmCraft project, or canonical promotion path.

## Start

One pass:

```powershell
$env:VAULT_WORKSPACE_ROOT = "C:\path\to\vault"
$env:NVIDIA_API_KEY = "nvapi-..."
$env:WHITE_STUDIO_ALLOW_EXTERNAL_EMBEDDING = "1"
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

The idle gate requires both `NVIDIA_API_KEY` (or `NVAPI_API_KEY`) and the
explicit `WHITE_STUDIO_ALLOW_EXTERNAL_EMBEDDING=1` consent flag. A credential
alone never authorizes sending Vault text to NVIDIA. Without either condition,
the worker pauses before creating a durable embedding task; it does not spend
an API call or record a false failure. The consent flag is local process policy,
not a canonical Vault setting, and it does not include ChatGPT memory data in
the eligible source set.

The same consent check is enforced inside `IdleBackgroundWorker.run_once`,
so a direct library caller cannot bypass the launcher gate.

The idle worker, the foreground `AutonomyRunner`, and the Node Inbox daemon share
the configured application data root's `autonomy/task.lease`. On Windows this
defaults to the same `AppData\\Local\\Trevor` data root used by the runtime;
`WHITE_STUDIO_AUTONOMY_ROOT` can override it for an isolated test. The Node
daemon uses the same JSON lease and leaves a queued contract unchanged when the
lease is unavailable. This prevents an embedding batch from running concurrently
with Inbox or MCP execution. Foreground detection reads only the YAML frontmatter `status` of
`智能體/chatgpt-inbox.md` and `智能體/tasks/*.md`; historical body text is not
a task signal.

## Outputs

All outputs are derived runtime state under
`runtime/.mcp-state/embedding-index/`:

- `embedding-index.jsonl`: source-hashed passage vectors
- `checkpoint.json`: resumable cursor and operation identity
- `orchestrator/`: durable task and event projections
- `provenance.json`: source commit, manifest hash, model, and dimension
- `validation.json`: candidate validation result
- `canonical-index-proposal.json`: promotion proposal
- `idle-worker-heartbeat.json`: non-secret liveness, status, and operation identity

The heartbeat is replaced atomically after each worker pass. A stale heartbeat
is not proof that the worker is alive or that an embedding task succeeded; a
watchdog must check its timestamp and the durable task projection separately.

Use the read-only readiness probe to inspect the current local projection:

```powershell
py -3 tools/check_idle_worker_readiness.py
```

Run the isolated behavior verifier before enabling a worker or scheduling it:

```powershell
py -3 tools/verify_idle_background_e2e.py
```

It uses a temporary Vault and fake embedding provider. `PASS` proves
checkpoint recovery, foreground preemption, shared-lease exclusion, source
filtering, and the canonical approval gate without contacting NVIDIA or
modifying the user's Vault.

The probe distinguishes configuration readiness from observed checkpoint and
preemption evidence. It always reports canonical promotion as disabled; a
proposal is not an approval.

The worker never edits formal canonical Markdown or applies canonical
promotion. A promotion must be reviewed separately.

## Preemption and failure

- Foreground task: checkpoint and persist the durable task as `paused`.
- User activity: policy pause.
- CPU at or above 80%: policy pause.
- Memory at or above 85%: policy pause.
- API failure: checkpoint and block/defer. The client preserves actionable
  reasons: `embedding_auth_failed` for 401, `embedding_rate_limited` for 429,
  and `embedding_timeout` for timeout. Authentication, schema, and integrity
  failures become `blocked`. Rate limiting and timeout become `deferred` with
  a bounded checkpoint backoff (maximum three deferrals by default); the
  embedding request itself is never retried inside one batch.
- Missing or invalid vectors: block. No partial success is reported.
- `paused` means expected preemption and is resumable from the checkpoint;
- `deferred` means transient provider pressure and is resumable after the
  checkpoint deadline; it is not a successful completion and is bounded;
  `blocked` means an error or integrity condition requires inspection.
- The loop sleeps until the deferred checkpoint deadline, subject to its
  normal polling floor, so provider pressure does not create a busy poll.
- Existing `source_path + sha256 + model_id`: skip as duplicate.
- The checkpoint stores the source manifest hash and source commit. If the
  eligible Markdown set or any source bytes change between batches, the worker
  stops with `source_manifest_changed` instead of continuing from a stale
  cursor. A legacy checkpoint without a manifest is blocked when its cursor is
  non-zero (`source_manifest_missing`).

Nemotron-3-Embed-1B uses `passage` for indexing and `query` for retrieval.
It is not a chat or tool-calling model.
