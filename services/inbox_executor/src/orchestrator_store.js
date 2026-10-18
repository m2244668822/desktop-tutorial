import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const TERMINAL = new Set(["done", "blocked", "failed"]);
const TRANSITIONS = new Map([
  ["queued", new Set(["claimed", "running", "blocked", "failed"])],
  ["claimed", new Set(["running", "blocked", "failed"])],
  ["running", new Set(["validating", "blocked", "failed"])],
  ["validating", new Set(["done", "blocked", "failed"])],
  ["done", new Set()],
  ["blocked", new Set()],
  ["failed", new Set()],
]);

function safeName(value) {
  const raw = String(value || "");
  const safe = raw.replace(/[^a-zA-Z0-9._-]+/g, "-").slice(0, 100) || "unknown";
  return `${safe}-${crypto.createHash("sha256").update(raw).digest("hex").slice(0, 12)}`;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function atomicWrite(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.${process.pid}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  fs.writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  fs.renameSync(temp, file);
}

export function newOperationContext(taskId, requestedBy = "inbox-daemon", seed = "") {
  const task = String(taskId || "task");
  const digest = crypto.createHash("sha256").update(`${task}\n${seed}`).digest("hex");
  return {
    task_id: task,
    run_id: `run-${crypto.randomUUID()}`,
    operation_id: `op-${crypto.randomUUID()}`,
    idempotency_key: `inbox:${task}:${digest.slice(0, 24)}`,
    requested_by: requestedBy,
  };
}

export function createOrchestratorStore(root) {
  const stateRoot = path.resolve(root);
  const eventsPath = path.join(stateRoot, "events.jsonl");
  const tasksDir = path.join(stateRoot, "tasks");
  const idempotencyDir = path.join(stateRoot, "idempotency");

  function taskPath(taskId) {
    return path.join(tasksDir, `${safeName(taskId)}.json`);
  }

  function idempotencyPath(key) {
    return path.join(idempotencyDir, `${safeName(key)}.json`);
  }

  function readJson(file) {
    if (!fs.existsSync(file)) return null;
    return JSON.parse(fs.readFileSync(file, "utf8"));
  }

  function appendEvent(event) {
    fs.mkdirSync(stateRoot, { recursive: true });
    fs.appendFileSync(eventsPath, `${JSON.stringify(event)}\n`, "utf8");
  }

  function writeProjection(record) {
    atomicWrite(taskPath(record.task_id), record);
    if (record.idempotency_key) atomicWrite(idempotencyPath(record.idempotency_key), {
      task_id: record.task_id,
      run_id: record.run_id,
      operation_id: record.operation_id,
      idempotency_key: record.idempotency_key,
      status: record.status,
    });
  }

  function get(taskId) {
    return readJson(taskPath(taskId));
  }

  function lookupIdempotency(key) {
    const ref = readJson(idempotencyPath(key));
    return ref ? get(ref.task_id) : null;
  }

  function create(record) {
    const next = {
      status: "queued",
      validation_status: "pending",
      created_at: new Date().toISOString(),
      ...clone(record),
    };
    if (!next.task_id || !next.run_id || !next.operation_id || !next.idempotency_key) {
      throw new Error("orchestrator_identity_required");
    }
    const existing = lookupIdempotency(next.idempotency_key);
    if (existing) {
      if (existing.task_id !== next.task_id) throw new Error("idempotency_key_conflict");
      return existing;
    }
    if (get(next.task_id)) throw new Error("task_already_exists");
    writeProjection(next);
    appendEvent({ type: "task.created", at: next.created_at, task: next });
    return clone(next);
  }

  function transition(taskId, status, changes = {}) {
    const current = get(taskId);
    if (!current) throw new Error("task_not_found");
    if (current.status !== status) {
      const allowed = TRANSITIONS.get(current.status) || new Set();
      if (!allowed.has(status)) {
        throw new Error(`invalid_task_transition:${current.status}->${status}`);
      }
    }
    const next = {
      ...current,
      ...clone(changes),
      status,
      updated_at: new Date().toISOString(),
    };
    if (TERMINAL.has(status) && !next.completed_at) next.completed_at = next.updated_at;
    writeProjection(next);
    appendEvent({
      type: "task.transition",
      at: next.updated_at,
      task_id: taskId,
      from: current.status,
      to: status,
      changes: clone(changes),
    });
    return clone(next);
  }

  function recoverStaleTasks({ maxAgeSeconds = 900, now = Date.now() } = {}) {
    const active = new Set(["claimed", "running", "validating"]);
    const threshold = Math.max(0, Number(maxAgeSeconds) || 0);
    const currentTime = now instanceof Date ? now.getTime() : Number(now);
    const recovered = [];
    if (!Number.isFinite(currentTime) || !fs.existsSync(tasksDir)) return recovered;
    for (const name of fs.readdirSync(tasksDir)) {
      if (!name.endsWith(".json")) continue;
      const record = readJson(path.join(tasksDir, name));
      if (!record || !active.has(record.status)) continue;
      const updated = Date.parse(String(record.updated_at || ""));
      if (!Number.isFinite(updated)) continue;
      const ageSeconds = Math.max(0, (currentTime - updated) / 1000);
      if (ageSeconds <= threshold) continue;
      recovered.push(transition(record.task_id, "blocked", {
        validation_status: "failed",
        metadata: {
          ...(record.metadata || {}),
          blocked_reason: "stale_task_recovery",
          failure_phase: "recovery",
          requires_reconciliation: true,
          auto_retry: false,
          stale_for_seconds: Math.round(ageSeconds * 1000) / 1000,
        },
      }));
    }
    return recovered;
  }

  function rebuildProjection() {
    if (!fs.existsSync(eventsPath)) return [];
    const latest = new Map();
    for (const line of fs.readFileSync(eventsPath, "utf8").split(/\r?\n/).filter(Boolean)) {
      const event = JSON.parse(line);
      if (event.type === "task.created") latest.set(event.task.task_id, event.task);
      if (event.type === "task.transition") {
        const current = latest.get(event.task_id);
        if (current) latest.set(event.task_id, {
          ...current,
          ...event.changes,
          status: event.to,
          updated_at: event.at,
        });
      }
    }
    for (const record of latest.values()) writeProjection(record);
    return [...latest.values()].map(clone);
  }

  return {
    root: stateRoot,
    create,
    get,
    lookupIdempotency,
    transition,
    recoverStaleTasks,
    rebuildProjection,
  };
}

export function defaultOrchestratorStateRoot(vaultRoot) {
  return process.env.WHITE_STUDIO_ORCHESTRATOR_STATE_DIR ||
    path.join(vaultRoot, "runtime", ".mcp-state", "orchestrator");
}
