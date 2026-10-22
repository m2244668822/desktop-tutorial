import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { VaultWorkspace, dispatch } from "../../vault_workspace_mcp/src/workspace.js";
import {
  acquireLease,
  appendJournalTransition,
  assertLeaseFence,
  buildRollbackManifest,
  computeStateHash,
  evaluateProjectPolicy,
  idempotencyDecision,
  readJournal,
  releaseLease,
} from "./transaction.js";

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2) + "\n", "utf8");
}

async function phase(name, fn) {
  const started = new Date().toISOString();
  try {
    const evidence = await fn();
    return { name, status: "pass", started_at: started, finished_at: new Date().toISOString(), evidence };
  } catch (error) {
    return { name, status: "fail", started_at: started, finished_at: new Date().toISOString(), error: String(error?.message || error) };
  }
}

async function main() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "white-studio-phase-acceptance-"));
  const stateRoot = path.join(root, "runtime", ".mcp-state");
  const journalPath = path.join(stateRoot, "operation-journal.jsonl");
  fs.mkdirSync(stateRoot, { recursive: true });
  writeJson(path.join(root, "runtime", "test-profiles.json"), {
    policy: { unknown_project: "blocked" },
    projects: {
      "phase-e-registered": {
        root: ".",
        automation_mode: "bounded_write",
        policy_scope: "disposable-acceptance",
        allowed_write_tools: ["workspace.create", "workspace.patch", "workspace.move", "workspace.trash"],
      },
    },
  });

  const workspace = new VaultWorkspace({
    workspaceRoot: root,
    auditDir: path.join(root, "runtime", ".mcp-audit"),
    trashDir: path.join(root, "runtime", ".mcp-trash"),
    autoApprove: true,
  });
  const leaseStore = path.join(stateRoot, "leases.json");
  const lease = acquireLease({ storePath: leaseStore, taskId: "phase-acceptance", executorId: "windows-local-acceptance", ttlMs: 30000 });
  const operationId = "op-phase-acceptance";
  const requestHash = "request-phase-acceptance";
  const common = {
    operation_id: operationId,
    task_id: "phase-acceptance",
    run_id: "run-phase-acceptance",
    lease_id: lease.lease_id,
    lease_generation: lease.lease_generation,
    fencing_token: lease.fencing_token,
    timestamp: new Date().toISOString(),
    executor_id: lease.executor_id,
    state_hash: "fixture-state",
    request_hash: requestHash,
    idempotency_key: "phase-key",
    evidence_ref: "phase_acceptance",
    error_code: null,
  };
  const results = [];

  results.push(await phase("A", () => {
    assert.doesNotThrow(() => assertLeaseFence({ storePath: leaseStore, lease }));
    const first = idempotencyDecision([], "phase-key", requestHash);
    assert.equal(first.action, "execute");
    appendJournalTransition(journalPath, { ...common, transition: "requested" });
    appendJournalTransition(journalPath, { ...common, transition: "authorized" });
    appendJournalTransition(journalPath, { ...common, transition: "executing" });
    const replay = idempotencyDecision(readJournal(journalPath), "phase-key", requestHash);
    assert.equal(first.action, "execute");
    assert.equal(replay.action, "execute");
    appendJournalTransition(journalPath, { ...common, transition: "completed", result: { ok: true } });
    const completedReplay = idempotencyDecision(readJournal(journalPath), "phase-key", requestHash);
    assert.equal(completedReplay.action, "replay");
    assert.equal(idempotencyDecision(readJournal(journalPath), "phase-key", "different-request").code, "HARD_CONFLICT");
    return { lease_generation: lease.lease_generation, fencing_token: lease.fencing_token, idempotency: "replay_and_hard_conflict" };
  }));

  results.push(await phase("B", () => {
    assert.equal(evaluateProjectPolicy({ vaultRoot: root, projectId: "phase-e-registered", tool: "workspace.read" }).ok, true);
    assert.equal(evaluateProjectPolicy({ vaultRoot: root, projectId: "unknown", tool: "workspace.patch" }).code, "unknown_project");
    const state = computeStateHash({ head: "fixture", trackedChangedPaths: [], targetFileBlobHashes: {}, policyMetadata: { phase: "B" }, projectId: "phase-e-registered", projectFingerprint: "fixture" });
    assert.equal(state.hash, computeStateHash({ head: "fixture", trackedChangedPaths: [], targetFileBlobHashes: {}, policyMetadata: { phase: "B" }, projectId: "phase-e-registered", projectFingerprint: "fixture" }).hash);
    return { read_only_policy: "pass", deterministic_hash: "pass" };
  }));

  const initial = path.join(root, "draft.md");
  results.push(await phase("C", async () => {
    await dispatch(workspace, "workspace.create", { path: "draft.md", content: "S0" });
    await dispatch(workspace, "workspace.patch", { path: "draft.md", content: "S1" });
    assert.equal(fs.readFileSync(initial, "utf8"), "S1");
    return { create: "pass", patch: "pass" };
  }));

  results.push(await phase("D", async () => {
    const moved = await dispatch(workspace, "workspace.move", { from: "draft.md", to: "archive/draft.md" });
    const moveManifest = buildRollbackManifest({ tool: "workspace.move", args: { from: "draft.md", to: "archive/draft.md" }, result: moved, beforeStateHash: "state-before-move" });
    const trashed = await dispatch(workspace, "workspace.trash", { path: "archive/draft.md" });
    const trashManifest = buildRollbackManifest({ tool: "workspace.trash", args: { path: "archive/draft.md" }, result: trashed, beforeStateHash: "state-before-trash" });
    assert.equal(moveManifest.requires_approval, true);
    assert.equal(trashManifest.requires_approval, true);
    return { move_rollback: moveManifest.action, trash_rollback: trashManifest.action };
  }));

  results.push(await phase("E", () => {
    const policy = evaluateProjectPolicy({ vaultRoot: root, projectId: "phase-e-registered", tool: "workspace.patch", targetPath: "draft.md" });
    assert.equal(policy.ok, true);
    assert.equal(evaluateProjectPolicy({ vaultRoot: root, projectId: "phase-e-registered", tool: "workspace.patch", targetPath: "canonical/frozen.md" }).code, "protected_target");
    return { registered_profile: "phase-e-registered", bounded_write: "pass", protected_target: "pass" };
  }));

  releaseLease({ storePath: leaseStore, lease });
  const report = {
    schema_version: "1.0.0",
    kind: "windows_phase_a_e_acceptance",
    generated_at: new Date().toISOString(),
    runtime: { node: process.version, platform: process.platform, arch: process.arch },
    fixture_root: root,
    phases: results,
    overall: results.every((item) => item.status === "pass") ? "PASS" : "FAIL",
    scope: "isolated disposable fixture; not production readiness evidence",
  };
  const output = process.argv[2] === "--output" ? process.argv[3] : "";
  if (output) writeJson(path.resolve(output), report);
  console.log(JSON.stringify(report, null, 2));
  if (report.overall !== "PASS") process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
