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
