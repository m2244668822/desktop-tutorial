# White Studio MCP Contract v1

Status: implementation contract

This contract separates tool capability from model choice. A model may propose a
tool call, but the orchestrator must validate the schema and policy before it
executes the call.

## Operation identity

Every call carries `task_id`, `run_id`, `operation_id`, and
`idempotency_key`. The caller must also provide `capability` and, for writes,
`project_id` and `project_fingerprint`.

For the local stdio adapter, these fields are transported in MCP call metadata
under `params._meta.whiteStudio`. The adapter accepts `_context` inside tool
arguments only as a compatibility path, removes it before forwarding to the
FilmCraft wire tool, and never sends identity metadata to FilmCraft itself.
Missing identity is a fail-closed `schema_invalid:identity` error.

When the Python Orchestrator calls the in-process `FilmCraftMcpAdapter`, it uses
the same contextual boundary (`call_with_context`). The adapter retains the
identity locally and forwards only FilmCraft-native arguments upstream. This
keeps host protocol metadata and FilmCraft protocol metadata separate.

## Capability levels

| Level | Meaning | Default policy |
|---|---|---|
| `read` | Inspect or compare state | Automatic when the server is available |
| `disposable_write` | Write only to an explicitly disposable project | Snapshot, readback, and undo required |
| `real_write` | Write to a real user project | Separate user authorization required |
| `remote_deploy` | Deploy or mutate a remote service | Separate deployment review required |

`project_id = current` and ambiguous paths are invalid for every write.

The mutation entry point accepts only `disposable_write` or `real_write`.
Passing `read`, `remote_deploy`, or an unknown capability to a mutation is a
policy error before any MCP call is sent.

Read tools must use the durable read entry point. A read entry point rejects
write tools before dispatch, records the same task/run/operation identity, and
returns a `read_only=true` result envelope.

Model-generated tool calls are proposals only. `execute_tool_proposal` routes
read proposals to the read path; write proposals require an explicit write
capability, project target, fingerprint, and the normal policy gate. Unknown
proposals are denied before dispatch. A model response never grants itself MCP
permission.

Before the first `tools/call`, an adapter must perform `tools/list` and cache
the current tool names and input schemas for that session. An unavailable or
malformed discovery response is a fail-closed `tools_list_invalid` result; an
unknown wire tool is `tool_unavailable`. Before dispatch, required fields and
declared primitive types are checked; invalid arguments are a fail-closed
`schema_invalid` result. The adapter must not discover a missing tool or defer
schema validation until after attempting a write.

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
| `state_compare` | local validator | yes | yes | n/a |

`state_compare` is an orchestrator-local validator. It compares the supplied
before/after snapshots and must never be sent to the FilmCraft wire
`tools/call` endpoint. The FilmCraft adapter only exposes its discovered wire
tools; the orchestrator records the local comparison as a separate durable
validation event.

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

The local adapter also keeps a process-local idempotency cache. Reusing the
same key with the same tool and arguments returns the original result without
repeating the mutation. Reusing it with different arguments returns
`idempotency_conflict`. Durable recovery remains the orchestrator's
responsibility; a process restart does not turn this cache into durable truth.

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

Read-only calls and state snapshots may retry once after a transport failure.
Mutation and undo calls are never automatically retried; a safe retry requires
reconciliation and a new approved operation identity.

For FilmCraft, the reliable undo path is:

```text
command_run → edit.undo → state_snapshot → state_compare
```

Headless keyboard shortcuts are not undo evidence.

## Local FilmCraft adapter process

`tools/filmcraft_mcp_adapter.py` is the local stdio bridge for MCP hosts. It
starts the installed FilmCraft CLI's own MCP process and exposes this contract
without exposing the CLI's unrestricted UI tools by default:

```text
MCP host
  -> tools/filmcraft_mcp_adapter.py
  -> filmcraft-cli.exe mcp
```

The disposable verification command is:

```powershell
py -3 -B -m unittest tests.test_filmcraft_mcp_adapter_server
```

`--demo` is the only mode that permits writes without an additional launch
flag. Real-project mode requires an explicit project path, project id,
project fingerprint, and `--allow-real-write`; omitting any of these fails
closed. Host registration remains disabled until a user explicitly approves
the host configuration and the runtime doctor reports the current tool call.

## Durable failure semantics

If a mutation, post-write readback, undo call, or S0/S3 comparison raises an
error, the orchestrator must persist the task as `blocked` with
`validation_status=failed`. The record must retain a machine-readable
`blocked_reason`, `failure_phase`, and `requires_reconciliation=true`; it must
never remain `running` and must never be converted into `completed`.

After an interrupted process, `recover_stale_tasks` may mark stale
`claimed`/`running`/`validating` records as `blocked` when their durable
`updated_at` exceeds the configured threshold. It never recovers `queued`
records and never replays a mutation. Recovery sets `auto_retry=false` and
requires reconciliation against the external project before a new operation
identity is approved.

The Python Orchestrator, idle worker, Inbox daemon, and agentic executor invoke
this recovery check at startup. The threshold is operational configuration;
it must be longer than the maximum expected foreground operation. A recovery
event is evidence of interruption handling, not evidence that the original
operation succeeded or failed at the external service.

An operation with the same `idempotency_key` must not be sent again while its
durable record is `running`, `blocked`, `failed`, or `completed`. Recovery must
first inspect the operation record and current project state, then use a new
approved operation identity if a retry is actually safe.

Each MCP call also emits `mcp_call_started` and `mcp_call_finished` events.
These events carry identity, tool, phase, success, and hashes of arguments or
responses. They must not persist raw tool arguments or raw provider payloads.
