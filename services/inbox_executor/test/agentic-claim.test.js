import assert from "node:assert/strict";
import test from "node:test";
import { upsertExecutorClaim } from "../src/executor_identity.js";

test("agentic claim preserves the remote task revision for CAS writeback", () => {
  const text = "---\nstatus: queued\n---\n\n# task\n";
  const claimed = upsertExecutorClaim(text, "task-r3", {
    executor_id: "codex",
    executor_type: "headless",
    executor_provider: "openai",
    executor_product: "codex",
    executor_mode: "headless",
    executor_version: "test",
    executor_capabilities: ["bounded-tests"],
    claimed_at: "2026-10-23T00:00:00.000Z",
  }, "revision-r3");

  assert.match(claimed, /- remote_task_revision：`revision-r3`/);
});

test("claim preserves formal execution identifiers before policy denial", () => {
  const text = "---\nstatus: queued\n---\n\n# task\n";
  const claimed = upsertExecutorClaim(
    text,
    "task-policy-denial",
    {
      executor_id: "github-actions-self-hosted",
      executor_type: "external",
      executor_provider: "github",
      executor_product: "actions-runner",
      executor_mode: "self-hosted-windows",
      executor_version: "actions-runner",
      executor_capabilities: ["bounded-tests"],
      claimed_at: "2026-11-07T01:00:00.000Z",
    },
    "revision-policy-denial",
    {
      run_id: "run-policy-denial",
      operation_id: "op-policy-denial",
      lease_id: "lease-policy-denial",
      lease_generation: 1,
      fencing_token: "fence-policy-denial",
    }
  );

  assert.match(claimed, /- run_id：`run-policy-denial`/);
  assert.match(claimed, /- operation_id：`op-policy-denial`/);
  assert.match(claimed, /- lease_id：`lease-policy-denial`/);
  assert.match(claimed, /- fencing_token：`fence-policy-denial`/);
});
