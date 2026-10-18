# Chat Model Gateway

`core/chat_gateway.py` is the single chat entry point for the local
Orchestrator. It is separate from MCP permissions and from the embedding
client.

## Routing rules

```text
private/local request
  -> local provider only

redacted/public request
  -> eligible providers by priority
  -> bounded provider fallback

all providers unavailable
  -> ChatGatewayBlocked
```

`nvidia/nemotron-3-embed-1b` is an embedding provider. It must be registered
with `capabilities={"embedding"}` and is rejected by the chat gateway.

## Response identity

Every successful response keeps the caller's `task_id` and `run_id`. The
response also records the selected model and the ordered attempted models.
The gateway does not create or authorize MCP tool calls.

`Orchestrator.run_chat()` is the durable entry point around the gateway. It
records `queued -> running -> completed` or `blocked`, keeps `task_id` and
`run_id`, and stores provider identity without storing credentials or raw
provider payloads. A blocked provider never becomes a fake successful reply.

The existing `DesktopBridge` exposes this path by explicit opt-in:

```json
{"model": "orchestrated", "message": "..."}
```

`orchestrated` uses local privacy routing. `orchestrated-cloud` allows a
configured cloud candidate, but still keeps the same policy and durable task
boundary. Existing `model=auto` behavior is unchanged until the opt-in path
has a live provider review.

## Provider integration

Use `RegistryChatTransport` with the existing `ProviderRegistry` and
`ProviderHttpClient` when an API provider is configured. Use
`OllamaChatTransport` for a local provider. The local transport has no API
credential path. Credentials for cloud providers remain in the existing
credential resolver or process environment; they are not part of the gateway
response or task payload.

The local provider must be marked `availability="online"` only after the
Ollama health probe succeeds. A configured model name alone is not proof that
the model is installed.

### OpenRouter Nemotron chat

For a free, rate-limited text chat candidate, configure the existing provider
registry without placing credentials in source files:

```text
OPENROUTER_API_KEY=<local credential>
OPENROUTER_FREE_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
```

The `:free` suffix is required by the registry cost gate. This provider is a
cloud candidate, not a private Vault default and not an embedding provider.
Use local routing for private content unless an explicit redaction policy
allows cloud transfer.

OpenRouter reasoning continuation can be requested through `ChatRequest`:

```python
ChatRequest(
    task_id="task-...",
    run_id="run-...",
    messages=messages,
    privacy_class="cloud",
    extra_body={"reasoning": {"enabled": True}},
)
```

When a follow-up request reuses an assistant message, preserve its
`reasoning_details` field unchanged. The HTTP adapter also preserves tool
fields in message records. `ProviderHttpClient.call()` remains text-only for
legacy callers; `call_with_metadata()` and `RegistryChatTransport` expose the
opaque fields only to the chat continuation path. Do not log those fields or
copy them into task state. The opt-in DesktopBridge path keeps the latest
assistant reasoning fields in memory for the active session only; it does not
persist them to the durable task store. The fields are forwarded only when
the next turn remains on the same configured cloud model. Switching to local
Ollama or another model drops the opaque fields.

`ChatResponse.as_assistant_message()` is the supported continuation helper. It
returns the assistant role/content plus the unchanged opaque fields. It does
not execute `tool_calls`; proposed tool calls still pass through the separate
policy and MCP orchestrator path. For a follow-up, use
`ChatModelGateway.continue_chat(request, response, user_content)`. It pins the
next call to `response.model_id`; if that exact model is unavailable, the
continuation is blocked instead of sending provider-specific reasoning data to
a fallback model.

## Current boundary

This is a ready, test-covered program layer. It does not claim that a local
chat model is installed or healthy. A provider becomes routable only after it
is registered and reports `availability="online"`.
