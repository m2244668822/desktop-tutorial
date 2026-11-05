# Conversation Event MVP

This module is the first executable bridge between a chat turn and White Studio's governed backend.

It does **not** infer hidden meaning by itself. The conversational planner supplies structured proposals; this deterministic layer validates and downgrades them into governed states.

## Flow

```text
chat turn
→ ConversationEvent
→ user claim candidates
→ permission decisions
→ task result skeleton
→ existing queue / MCP / Codex layers
```

## Safety invariants

- A proposed user-model update always enters as `CANDIDATE`.
- The planner cannot force `APPROVED` by putting that value in input JSON.
- Low-risk `READ / SEARCH / INFER / PROPOSE` actions can be `ALLOW`.
- `UPDATE_USER_MODEL / WRITE_KNOWLEDGE / MODIFY_FILE` require human approval.
- `DELETE / CHANGE_POLICY / EXPAND_PERMISSION` are denied in v0.1.
- A new task result starts as `UNVERIFIED`; success requires later execution evidence and verification.

## Run locally

```bash
cd services/inbox_executor
node src/conversation_event_e2e.js
```

Process one event from a JSON file:

```bash
node src/conversation_event_cli.js ./event.json
```

Or from stdin:

```bash
type event.json | node src/conversation_event_cli.js
```

This MVP intentionally stops before automatic persistence. The next bounded step is to connect the normalized output to the durable queue, then use the existing executor router for MCP/Codex execution.
