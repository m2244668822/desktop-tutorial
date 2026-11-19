// Ported from Runtime ad4ffa1 for the single-process Phase A–E fixture.
// Each run owns its lease store and journal in a new temporary directory.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, stableValue(value[key])])
    );
  }
  return value;
}

function stableJson(value) {
  return JSON.stringify(stableValue(value));
}

function sha256(value) {
  return crypto.createHash("sha256").update(String(value), "utf8").digest("hex");
}

export function computeStateHash({
  head = "",
  trackedChangedPaths = [],
  targetFileBlobHashes = {},
  policyMetadata = {},
  projectId = "",
  projectFingerprint = "",
}) {
  const lines = [
    "HEAD=" + String(head),
    "project_fingerprint=" + String(projectFingerprint),
    "project_id=" + String(projectId),
    "policy_metadata=" + stableJson(policyMetadata),
    ...Object.keys(targetFileBlobHashes)
      .map((item) => item.replace(/\\/g, "/"))
      .sort()
      .map((item) => "target_blob=" + item + "=" + String(targetFileBlobHashes[item])),
    ...[...new Set(trackedChangedPaths.map((item) => item.replace(/\\/g, "/")))]
      .sort()
      .map((item) => "tracked_changed_path=" + item),
  ];
  return { hash: sha256(lines.join("\n") + "\n"), lines };
}

function readJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    return fallback;
  }
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const temp = filePath + "." + process.pid + ".tmp";
  fs.writeFileSync(temp, JSON.stringify(value, null, 2) + "\n", "utf8");
  fs.renameSync(temp, filePath);
}

export function acquireLease({ storePath, taskId, executorId, now = new Date().toISOString(), ttlMs = 30000 }) {
  const store = readJson(storePath, { version: 1, leases: {} });
  const previous = store.leases[taskId];
  const nowMs = Date.parse(now);
  if (previous && Date.parse(previous.expires_at) > nowMs) {
    throw Object.assign(new Error("lease_held"), { code: "lease_held", lease: previous });
  }
  const generation = Number(previous?.lease_generation || 0) + 1;
  const lease = {
    task_id: taskId,
    lease_id: crypto.randomUUID(),
    lease_generation: generation,
    fencing_token: crypto.randomUUID(),
    executor_id: executorId,
    acquired_at: now,
    expires_at: new Date(nowMs + ttlMs).toISOString(),
    heartbeat_at: now,
  };
  store.leases[taskId] = lease;
  writeJson(storePath, store);
  return lease;
}

export function assertLeaseFence({ storePath, lease, now = new Date().toISOString() }) {
  const store = readJson(storePath, { version: 1, leases: {} });
  const current = store.leases[lease.task_id];
  if (!current || current.lease_id !== lease.lease_id) {
    throw Object.assign(new Error("stale_lease"), { code: "stale_lease" });
  }
  if (
    current.lease_generation !== lease.lease_generation ||
    current.fencing_token !== lease.fencing_token ||
    current.executor_id !== lease.executor_id
  ) {
    throw Object.assign(new Error("stale_fencing_token"), { code: "stale_fencing_token" });
  }
  if (Date.parse(current.expires_at) <= Date.parse(now)) {
    throw Object.assign(new Error("lease_expired"), { code: "lease_expired" });
  }
  return current;
}

export function releaseLease({ storePath, lease }) {
  const store = readJson(storePath, { version: 1, leases: {} });
  const current = store.leases[lease.task_id];
  if (current?.lease_id === lease.lease_id && current?.fencing_token === lease.fencing_token) {
    delete store.leases[lease.task_id];
    writeJson(storePath, store);
    return true;
  }
  return false;
}

export function appendJournalTransition(journalPath, event) {
  const required = [
    "operation_id", "task_id", "run_id", "lease_id", "lease_generation",
    "fencing_token", "timestamp", "executor_id", "state_hash", "request_hash",
    "evidence_ref", "error_code", "transition",
  ];
  for (const field of required) {
    if (event[field] === undefined) {
      throw Object.assign(new Error("journal_field_missing:" + field), { code: "journal_field_missing" });
    }
  }
  fs.mkdirSync(path.dirname(journalPath), { recursive: true });
  fs.appendFileSync(journalPath, JSON.stringify(event) + "\n", "utf8");
  return event;
}

export function readJournal(journalPath) {
  if (!fs.existsSync(journalPath)) return [];
  return fs.readFileSync(journalPath, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

export function idempotencyDecision(journalRows, idempotencyKey, requestHash) {
  const rows = journalRows.filter((row) => row.idempotency_key === idempotencyKey);
  if (rows.length === 0) return { action: "execute" };
  if (rows.find((row) => row.request_hash !== requestHash)) {
    return { action: "deny", code: "HARD_CONFLICT" };
  }
  const completed = [...rows].reverse().find((row) => row.transition === "completed");
  return completed
    ? { action: "replay", result: completed.result }
    : { action: "execute" };
}

export function buildRollbackManifest({ tool, args = {}, result = {}, beforeStateHash = "" }) {
  const target = args.path || args.source || "";
  if (tool === "workspace.move") {
    return {
      kind: "move",
      action: "move_back",
      from: result.to || args.to,
      to: result.from || args.from,
      before_state_hash: beforeStateHash,
      requires_approval: true,
    };
  }
  if (tool === "workspace.trash") {
    return {
      kind: "soft_trash",
      action: "restore_from_trash",
      from: result.trash_path,
      to: result.from || target,
      before_state_hash: beforeStateHash,
      requires_approval: true,
    };
  }
  throw new Error("rollback_tool_not_supported");
}

function loadAutomationPolicy(vaultRoot) {
  const filePath = path.join(vaultRoot, "runtime", "test-profiles.json");
  return readJson(filePath, { policy: { unknown_project: "blocked" }, projects: {} });
}

export function evaluateProjectPolicy({ vaultRoot, projectId, tool, targetPath = "" }) {
  const config = loadAutomationPolicy(vaultRoot);
  const project = config.projects?.[projectId];
  const readTools = new Set([
    "workspace.list", "workspace.search", "workspace.read",
    "workspace.propose_patch", "runtime.capabilities",
  ]);
  if (!project) return { ok: false, code: "unknown_project", projectId, targetPath };
  const mode = project.automation_mode || "disabled";
  const projectRoot = String(project.root || ".").replace(/\\/g, "/").replace(/^\.\//, "").replace(/\/$/, "") || ".";
  if (readTools.has(tool)) {
    return { ok: true, mode, projectId, policyScope: project.policy_scope || projectId };
  }
  if (mode === "manual_only") {
    return { ok: false, code: "manual_only_project", projectId, targetPath };
  }
  if (mode !== "bounded_write") {
    return { ok: false, code: "automation_disabled", projectId, targetPath };
  }
  const allowedTestTools = new Set(project.allowed_test_tools || []);
  if (allowedTestTools.has(tool)) {
    return {
      ok: true,
      mode,
      projectId,
      projectRoot,
      policyScope: project.policy_scope || projectId,
    };
  }
  const normalizedTarget = targetPath.replace(/\\/g, "/");
  if (
    normalizedTarget &&
    projectRoot !== "." &&
    normalizedTarget !== projectRoot &&
    !normalizedTarget.startsWith(projectRoot + "/")
  ) {
    return { ok: false, code: "cross_project_target", projectId, targetPath };
  }
  if (/(^|\/)(canonical|frozen)(\/|$)|(^|\/)(\.env|secrets?)(\/|$)/i.test(normalizedTarget)) {
    return { ok: false, code: "protected_target", projectId, targetPath };
  }
  const allowed = new Set(project.allowed_write_tools || []);
  if (!allowed.has(tool)) {
    return { ok: false, code: "tool_not_allowed_by_project_policy", projectId, targetPath };
  }
  if (project.protected_patterns?.some((pattern) => new RegExp(pattern, "i").test(targetPath.replace(/\\/g, "/")))) {
    return { ok: false, code: "protected_target", projectId, targetPath };
  }
  return {
    ok: true,
    mode,
    projectId,
    projectRoot,
    policyScope: project.policy_scope || projectId,
  };
}
