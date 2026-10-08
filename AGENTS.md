# AGENTS.md

This repository supports unattended engineering tasks from White Studio / GitHub Inbox.

## Repository truth

Before editing, capture and report:

- repository root
- current branch
- HEAD SHA
- remote URL
- `git status --short`
- active executor identity

Never infer repository state from UI labels alone.

## Execution model

Valid execution surfaces:

- `workspace_mcp`: deterministic file/test tools.
- `codex`: headless coding executor when Codex CLI is installed and authenticated.
- `cursor`: headless coding executor when Cursor Agent CLI is installed and authenticated.
- `vscode`: editor/agent host and interactive handoff surface. Do not claim headless execution merely because `code` exists.

Mechanical tasks should use MCP without an LLM whenever possible.

## Workspace safety

Unattended agentic work must run in an isolated GitHub Actions checkout or an isolated worktree.

Never modify or clean a user's unrelated live worktree.

Forbidden by default:

- `git reset --hard`
- `git clean -fd` / `git clean -fdx`
- `git add -A`
- `git stash pop`
- force push
- destructive rebases of user work
- deleting unknown files
- modifying files outside the assigned workspace root
- reading or printing secrets
- unrestricted shell gateways

If existing dirty or untracked files could overlap the task, stop and report `workspace_conflict`.

## Change policy

Prefer the smallest change that satisfies the task.

Do not rewrite architecture, models, memory layers, or unrelated services unless the task explicitly requires it.

Do not silently switch execution providers.

## Tests and validation

Every code change must follow:

1. inspect relevant files
2. make the smallest patch
3. run targeted bounded tests
4. run broader configured bounded validation when appropriate
5. run `git diff --check`
6. report exact evidence

A test failure means the task is not `done`.

Do not invent PASS from historical logs.

## Repair budget

Automated repair loops are bounded.

Default maximum repair cycles: 3.

After the budget is exhausted, stop with:

`repair_budget_exhausted`

Do not loop indefinitely.

## Publication

Unless the task contract explicitly authorizes publication:

- do not merge `main`
- do not deploy
- do not force push
- do not rewrite protected branches

A reviewable branch / diff is the default endpoint.

## Result contract

Report at least:

- task_id
- route
- requested_executor
- selected_executor
- executor_identity
- project
- branch
- base_sha
- files_changed
- tests_run
- tests_passed
- tests_failed
- validation
- blockers
- started_at
- finished_at

Allowed terminal states:

- done
- blocked
- failed

Do not equate "input saved", "CLI installed", or "historical test passed" with successful execution.
