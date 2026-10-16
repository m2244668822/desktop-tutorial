import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createOrchestratorStore, newOperationContext } from "./orchestrator_store.js";

function makeStore() {
  return createOrchestratorStore(fs.mkdtempSync(path.join(os.tmpdir(), "ws-orchestrator-")));
}

test("durable store writes projection, event log, and rebuilds", () => {
  const store = makeStore();
  const context = newOperationContext("task-1", "test", "contract-a");
  const created = store.create({ ...context, capability: "read", tool_name: "workspace.read" });
  assert.equal(created.status, "queued");
  store.transition("task-1", "running");
  store.transition("task-1", "validating", { validation_status: "pending" });
  const done = store.transition("task-1", "done", { validation_status: "passed" });
  assert.equal(done.status, "done");
  assert.equal(store.lookupIdempotency(context.idempotency_key).task_id, "task-1");
  const rebuilt = store.rebuildProjection();
  assert.equal(rebuilt[0].status, "done");
  assert.equal(fs.readFileSync(path.join(store.root, "events.jsonl"), "utf8").trim().split(/\r?\n/).length, 4);
});

test("same idempotency key replays and conflicting task fails closed", () => {
  const store = makeStore();
  const context = newOperationContext("task-1", "test", "contract-a");
  store.create({ ...context });
  assert.equal(store.create({ ...context }).task_id, "task-1");
  assert.throws(() => store.create({ ...context, task_id: "task-2" }), /idempotency_key_conflict/);
});

test("invalid transition is rejected", () => {
  const store = makeStore();
  store.create({ ...newOperationContext("task-1") });
  assert.throws(() => store.transition("task-1", "done"), /invalid_task_transition/);
});
