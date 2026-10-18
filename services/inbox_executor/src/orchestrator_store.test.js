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

test("stale active task is blocked without automatic replay", () => {
  const store = makeStore();
  const context = newOperationContext("stale-task", "test", "contract-a");
  store.create({ ...context });
  store.transition("stale-task", "running");
  const taskFile = fs.readdirSync(path.join(store.root, "tasks"))[0];
  const taskPath = path.join(store.root, "tasks", taskFile);
  const record = JSON.parse(fs.readFileSync(taskPath, "utf8"));
  record.updated_at = "2026-10-17T00:00:00.000Z";
  fs.writeFileSync(taskPath, `${JSON.stringify(record, null, 2)}\n`, "utf8");

  const recovered = store.recoverStaleTasks({
    maxAgeSeconds: 900,
    now: Date.parse("2026-10-17T01:00:00.000Z"),
  });
  assert.equal(recovered.length, 1);
  assert.equal(recovered[0].status, "blocked");
  assert.equal(recovered[0].metadata.blocked_reason, "stale_task_recovery");
  assert.equal(recovered[0].metadata.requires_reconciliation, true);
  assert.equal(recovered[0].metadata.auto_retry, false);
  assert.deepEqual(
    store.recoverStaleTasks({ maxAgeSeconds: 900, now: Date.parse("2026-10-17T01:00:00.000Z") }),
    []
  );
});
