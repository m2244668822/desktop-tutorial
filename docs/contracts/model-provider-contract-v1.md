# White Studio Model Provider Contract v1

Status: implementation contract

The Model Router chooses a provider. It does not grant MCP permission and it
does not decide whether a project write is authorized.

## Provider record

```json
{
  "model_id": "local-qwen",
  "provider": "ollama",
  "roles": ["planner", "fallback"],
  "privacy_class": "local",
  "supports_tools": true,
  "supports_streaming": true,
  "supports_json_schema": true,
  "context_window": 32768,
  "max_output_tokens": 4096,
  "latency_class": "local",
  "cost_class": "local",
  "max_concurrency": 1,
  "priority": 1,
  "availability": "unknown"
}
```

`stream`, `structured_output`, and `tool_proposal` are optional capabilities.
The router must reject a request when the selected provider lacks a required
capability; it must not silently change the task policy.

Embedding is a separate provider capability. `nvidia/nemotron-3-embed-1b` is
registered for retrieval and indexing only. It is not a chat, planner,
executor, or tool-calling model. Document chunks use `input_type=passage`.
Search requests use `input_type=query`. The expected native vector dimension
is 2048.

## Roles

- `planner`: produces a plan or tool proposal; it cannot execute a tool.
- `executor`: consumes an approved proposal and returns operation identity.
- `validator`: reads results and compares state; it is not the executor.
- `fallback`: handles an approved retry path without expanding permissions.

## Required provider operations

Providers expose a normalized interface for `generate`, `health_check`, and
`tool_proposal`. `stream` and `structured_output` are enabled only when their
capability flags are true.

## Routing policy

1. Private Vault content routes to a local provider unless an explicit policy
   permits redaction and cloud transfer.
2. Complex planning may use the configured primary cloud provider.
3. Primary failure may select the configured fallback provider.
4. If no provider is healthy, the task becomes `blocked`.
5. Fallback cannot change `capability`, `project_id`, `project_fingerprint`,
   or authorization requirements.

## Reliability

Provider retries use a bounded count, timeout, exponential backoff, and jitter.
Model retries are independent from MCP mutation retries. The router must retain
`task_id` and `run_id` across every attempt and report provider health as
`online`, `degraded`, `rate_limited`, `overloaded`, or `unavailable`.

## Privacy and secrets

Credentials are resolved from the existing runtime credential path or process
environment. They are never written to the registry, task store, event log,
test output, or MCP result envelope.
