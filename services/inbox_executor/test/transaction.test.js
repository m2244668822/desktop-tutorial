import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  acquireLease,
  appendJournalTransition,
  assertLeaseFence,
  computeProjectFingerprint,
  computeStateHash,
  evaluateProjectPolicy,
  idempotencyDecision,
  readJournal,
  heartbeatLease,
  buildRollbackManifest,
  recoverOperation,
  validateResultWriteback,
} from "../src/transaction.js";

function tempState() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "white-studio-transaction-"));
  return { root, leasePath: path.join(root, "leases.json"), journalPath: path.join(root, "operations.jsonl") };
}

test("lease expiration increments generation and fences the old runner", () => {
  const { leasePath } = tempState();
  const first = acquireLease({
    storePath: leasePath,
    taskId: "task-1",
    executorId: "runner-a",
    now: "2026-10-22T00:00:00.000Z",
    ttlMs: 1000,
  });
  assert.equal(first.lease_generation, 1);
  assert.throws(
    () => acquireLease({
      storePath: leasePath,
      taskId: "task-1",
      executorId: "runner-b",
      now: "2026-10-22T00:00:00.500Z",
      ttlMs: 1000,
    }),
    (error) => error.code === "lease_held"
  );
  const second = acquireLease({
    storePath: leasePath,
    taskId: "task-1",
    executorId: "runner-b",
    now: "2026-10-22T00:00:02.000Z",
    ttlMs: 1000,
  });
  assert.equal(second.lease_generation, 2);
  assert.notEqual(second.fencing_token, first.fencing_token);
  assert.throws(
    () => assertLeaseFence({ storePath: leasePath, lease: first, now: "2026-10-22T00:00:02.100Z" }),
    (error) => error.code === "stale_fencing_token" || error.code === "stale_lease"
  );
  assert.doesNotThrow(() => assertLeaseFence({ storePath: leasePath, lease: second, now: "2026-10-22T00:00:02.100Z" }));
});

test("heartbeat extends an active lease but cannot revive an expired lease", () => {
  const { leasePath } = tempState();
  const lease = acquireLease({
    storePath: leasePath,
    taskId: "task-heartbeat",
    executorId: "runner-a",
    now: "2026-10-22T00:00:00.000Z",
    ttlMs: 1000,
  });
  const renewed = heartbeatLease({
    storePath: leasePath,
    lease,
    now: "2026-10-22T00:00:00.500Z",
    ttlMs: 1000,
  });
  assert.equal(renewed.heartbeat_at, "2026-10-22T00:00:00.500Z");
  assert.throws(
    () => heartbeatLease({ storePath: leasePath, lease: renewed, now: "2026-10-22T00:00:02.000Z" }),
    (error) => error.code === "lease_expired"
  );
});

test("state hash is deterministic and ignores unauthorized untracked noise", () => {
  const input = {
    head: "abc123",
    trackedChangedPaths: ["z.md", "a.md"],
    targetFileBlobHashes: { "z.md": "hash-z", "a.md": "hash-a" },
    policyMetadata: { project: "demo", scope: "bounded-write" },
    projectId: "demo",
    projectFingerprint: computeProjectFingerprint({ repoIdentity: "repo", normalizedRoot: "demo", policyScope: "bounded-write" }),
  };
  const first = computeStateHash(input);
  const second = computeStateHash({ ...input, unauthorizedUntrackedFiles: ["noise.tmp"] });
  assert.equal(first.hash, second.hash);
  assert.deepEqual(first.lines, [
    "HEAD=abc123",
    "project_fingerprint=" + input.projectFingerprint,
    "project_id=demo",
    "policy_metadata={\"project\":\"demo\",\"scope\":\"bounded-write\"}",
    "target_blob=a.md=hash-a",
    "target_blob=z.md=hash-z",
    "tracked_changed_path=a.md",
    "tracked_changed_path=z.md",
  ]);
});

test("operation journal is append-only and idempotency distinguishes replay from conflict", () => {
  const { journalPath } = tempState();
  const base = {
    operation_id: "op-1",
    task_id: "task-1",
    run_id: "run-1",
    lease_id: "lease-1",
    lease_generation: 1,
    fencing_token: "fence-1",
    timestamp: "2026-10-22T00:00:00.000Z",
    executor_id: "runner-a",
    state_hash: "state-1",
    request_hash: "request-1",
    evidence_ref: "audit-1",
    error_code: "",
  };
  appendJournalTransition(journalPath, { ...base, transition: "requested" });
  appendJournalTransition(journalPath, { ...base, transition: "authorized", timestamp: "2026-10-22T00:00:01.000Z" });
  const rows = readJournal(journalPath);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].transition, "requested");
  assert.equal(rows[1].transition, "authorized");
  assert.deepEqual(idempotencyDecision(rows, "key-1", "request-1"), { action: "execute" });
  const replayRows = [{ ...base, idempotency_key: "key-1", transition: "completed", result: { ok: true } }];
  assert.deepEqual(idempotencyDecision(replayRows, "key-1", "request-1"), {
    action: "replay",
    result: { ok: true },
  });
  assert.deepEqual(idempotencyDecision(replayRows, "key-1", "request-2"), {
    action: "deny",
    code: "HARD_CONFLICT",
  });
});

test("move and soft-trash produce approval-bound rollback manifests", () => {
  const moved = buildRollbackManifest({
    tool: "workspace.move",
    args: { from: "draft.md", to: "archive/draft.md" },
    result: { from: "draft.md", to: "archive/draft.md" },
    beforeStateHash: "s0",
  });
  assert.deepEqual(moved, {
    kind: "move",
    action: "move_back",
    from: "archive/draft.md",
    to: "draft.md",
    before_state_hash: "s0",
    requires_approval: true,
  });
  const trashed = buildRollbackManifest({
    tool: "workspace.trash",
    args: { path: "draft.md" },
    result: { from: "draft.md", trash_path: "runtime/.mcp-trash/draft.md" },
    beforeStateHash: "s0",
  });
  assert.equal(trashed.action, "restore_from_trash");
  assert.equal(trashed.requires_approval, true);
});

test("crash recovery chooses readback, publish, replay, or retry by journal state", () => {
  const base = { operation_id: "op-recovery", result: { ok: true }, error_code: "" };
  assert.deepEqual(recoverOperation([{ ...base, transition: "requested" }], "op-recovery"), {
    action: "retry_before_mutation",
  });
  assert.deepEqual(recoverOperation([{ ...base, transition: "executing" }], "op-recovery"), {
    action: "readback_before_retry",
  });
  assert.deepEqual(recoverOperation([{ ...base, transition: "validated" }], "op-recovery"), {
    action: "publish_result",
    result: { ok: true },
  });
  assert.deepEqual(recoverOperation([{ ...base, transition: "completed" }], "op-recovery"), {
    action: "replay",
    result: { ok: true },
  });
});

test("Result writeback requires lease ownership and the unchanged remote revision", () => {
  const lease = {
    lease_id: "lease-1",
    lease_generation: 3,
    fencing_token: "fence-3",
    executor_id: "runner-a",
  };
  assert.deepEqual(validateResultWriteback({
    taskId: "task-1",
    expectedTaskId: "task-1",
    lease,
    expectedLease: lease,
    remoteTaskRevision: "blob-1",
    expectedRemoteTaskRevision: "blob-1",
    remoteStatus: "queued",
  }), { ok: true, code: "result_writeback_authorized", mismatches: [] });
  const stale = validateResultWriteback({
    taskId: "task-1",
    expectedTaskId: "task-1",
    lease,
    expectedLease: { ...lease, lease_generation: 4 },
    remoteTaskRevision: "blob-1",
    expectedRemoteTaskRevision: "blob-2",
    remoteStatus: "running",
  });
  assert.equal(stale.ok, false);
  assert.equal(stale.code, "RESULT_NOT_PUBLISHED");
  assert.deepEqual(stale.mismatches, ["lease_generation", "remote_task_revision", "remote_status"]);
});

test("policy denies Primary Vault and allows only registered bounded projects", () => {
  const vaultRoot = path.resolve(import.meta.dirname, "../../../../..");
  const primary = evaluateProjectPolicy({
    vaultRoot,
    projectId: "obsidian-vault-refactor-2026-09-08",
    tool: "workspace.patch",
    targetPath: "README.md",
  });
  assert.equal(primary.ok, false);
  assert.equal(primary.code, "manual_only_project");
  const runtime = evaluateProjectPolicy({
    vaultRoot,
    projectId: "desktop-tutorial",
    tool: "workspace.patch",
    targetPath: "runtime/desktop-tutorial/services/inbox_executor/src/transaction.js",
  });
  assert.equal(runtime.ok, true);
  assert.equal(runtime.mode, "bounded_write");
  const protectedTarget = evaluateProjectPolicy({
    vaultRoot,
    projectId: "white-studio-web",
    tool: "workspace.patch",
    targetPath: "white-studio-web/canonical/current.md",
  });
  assert.equal(protectedTarget.ok, false);
  assert.equal(protectedTarget.code, "protected_target");
  const crossProject = evaluateProjectPolicy({
    vaultRoot,
    projectId: "desktop-tutorial",
    tool: "workspace.patch",
    targetPath: "white-studio-web/index.html",
  });
  assert.equal(crossProject.ok, false);
  assert.equal(crossProject.code, "cross_project_target");
});
