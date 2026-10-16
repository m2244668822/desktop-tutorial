# GitHub Inbox Polling Contract v1

Status: implementation contract

## Purpose

Keep Inbox execution automatic without allowing a stale local Vault to claim
or repeat a task. GitHub `main` is the queue source for unattended execution.

## Schedule

The workflow polls every five minutes and also supports `push` and manual
dispatch. A poll with no runnable task is a successful `queue_empty` no-op.

## Execution boundary

```text
GitHub main
  -> queue selector
  -> isolated Windows Runner checkout
  -> mechanical daemon or headless agent
  -> bounded validation
  -> exact task Result writeback
```

The primary dirty Vault is never used as the unattended checkout.

## Selection rules

1. Read only task files from the checked-out GitHub `main`.
2. Ignore `proposal`, `done`, `blocked`, and malformed contracts.
3. Select the highest priority runnable task.
4. Keep `task_id`, `run_id`, executor identity, and Result tied to the same
   task file.
5. Do not re-run a remote `done` or `blocked` task because a local copy is
   stale.

## Failure rules

- Runner offline: leave the remote task `queued`.
- No headless executor: write `blocked` with a reason; do not claim success.
- Agent failure: persist the Result before surfacing workflow failure.
- Push conflict: preserve the local Result as writeback-pending; do not force
  push or overwrite unrelated work.
- No task: return `queue_empty`; this is not an error.

## Required evidence

Each completed run must expose:

- workflow run URL and commit SHA;
- isolated Runner workspace path;
- selected task ID and route;
- executor identity;
- validation result;
- Result writeback commit or an explicit blocked reason.
