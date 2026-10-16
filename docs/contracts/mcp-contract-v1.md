# White Studio MCP Contract v1

Status: implementation contract

This contract separates tool capability from model choice. A model may propose a
tool call, but the orchestrator must validate the schema and policy before it
executes the call.

## Operation identity

Every call carries `task_id`, `run_id`, `operation_id`, and
`idempotency_key`. The caller must also provide `capability` and, for writes,
`project_id` and `project_fingerprint`.

## Capability levels

| Level | Meaning | Default policy |
|---|---|---|
| `read` | Inspect or compare state | Automatic when the server is available |
| `disposable_write` | Write only to an explicitly disposable project | Snapshot, readback, and undo required |
| `real_write` | Write to a real user project | Separate user authorization required |
| `remote_deploy` | Deploy or mutate a remote service | Separate deployment review required |

`project_id = current` and ambiguous paths are invalid for every write.

## Tool registry

| Tool | Capability | Read-only | Idempotent | Undo |
|---|---|---:|---:|---:|
| `project_inspect` | `read` | yes | yes | n/a |
| `sequence_inspect` | `read` | yes | yes | n/a |
| `marker_list` | `read` | yes | yes | n/a |
| `state_snapshot` | `read` | yes | yes | n/a |
| `markers_add` | `disposable_write` | no | caller key required | yes |
| `command_run` | `disposable_write` or `real_write` | no | command-specific | command-specific |
| `edit_undo` | `disposable_write` or `real_write` | no | operation-specific | recovery |
| `state_compare` | `read` | yes | yes | n/a |

## Result envelope

Successful mutation calls must return:

```json
{
  "success": true,
  "task_id": "task-example",
  "run_id": "run-example",
  "operation_id": "op-example",
  "project_id": "demo",
  "before_state_hash": "sha256:...",
  "after_state_hash": "sha256:...",
  "undo_available": true,
  "source": "filmcraft-adapter",
  "runtime_version": "0.8.0"
}
```

The orchestrator must not convert an MCP error into `success: true`.

State hashes use the adapter's canonical state. Runtime-only bookkeeping such
as FilmCraft's revision counter and dirty flag is retained in the raw audit
snapshot but is excluded from the semantic S0/S3 comparison.

## Error codes

`schema_invalid`, `authorization_required`, `project_required`,
`project_fingerprint_mismatch`, `idempotency_conflict`, `operation_unknown`,
`server_unavailable`, `tool_unavailable`, `timeout`, `readback_failed`,
`state_mismatch`, and `undo_unavailable` are stable machine-readable errors.

## Recovery semantics

Before retrying a mutation, inspect the operation log using `operation_id` and
`idempotency_key`. If the operation may have completed, read the project state
before sending another mutation. A retry is never allowed to bypass readback.

For FilmCraft, the reliable undo path is:

```text
command_run → edit.undo → state_snapshot → state_compare
```

Headless keyboard shortcuts are not undo evidence.
