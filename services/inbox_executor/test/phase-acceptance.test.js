import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { VaultWorkspace, dispatch } from "../../vault_workspace_mcp/src/workspace.js";
import {
  acquireLease,
  assertLeaseFence,
  buildRollbackManifest,
  computeStateHash,
  evaluateProjectPolicy,
  releaseLease,
} from "../src/transaction.js";

test("Phase A-E disposable project acceptance path", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "mcp-high-automation-phase-"));
  const state = path.join(root, "runtime", ".mcp-state");
  fs.mkdirSync(path.join(root, "runtime"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "runtime", "test-profiles.json"),
    JSON.stringify({
      policy: { unknown_project: "blocked" },
      projects: {
        "phase-demo": {
          root: ".",
          automation_mode: "bounded_write",
          policy_scope: "disposable",
          allowed_write_tools: ["workspace.create", "workspace.patch", "workspace.move", "workspace.trash"],
        },
      },
    }),
    "utf8"
  );
  const workspace = new VaultWorkspace({
    workspaceRoot: root,
    auditDir: path.join(root, "runtime", ".mcp-audit"),
    trashDir: path.join(root, "runtime", ".mcp-trash"),
    autoApprove: true,
  });
  const lease = acquireLease({
    storePath: path.join(state, "leases.json"),
    taskId: "phase-task",
    executorId: "phase-runner",
    ttlMs: 30000,
  });
  assert.doesNotThrow(() => assertLeaseFence({ storePath: path.join(state, "leases.json"), lease }));

  // Phase B: read-only capability and workspace read.
  assert.equal(evaluateProjectPolicy({ vaultRoot: root, projectId: "phase-demo", tool: "workspace.read" }).ok, true);
  const initial = computeStateHash({
    head: "fixture",
    trackedChangedPaths: [],
    targetFileBlobHashes: {},
    policyMetadata: { phase: "B" },
    projectId: "phase-demo",
    projectFingerprint: "fixture",
  });
  assert.equal(typeof initial.hash, "string");

  // Phase C: bounded create and patch on a disposable project.
  const created = await dispatch(workspace, "workspace.create", { path: "draft.md", content: "S0" });
  assert.equal(fs.readFileSync(path.join(root, "draft.md"), "utf8"), "S0");
  const patched = await dispatch(workspace, "workspace.patch", { path: "draft.md", content: "S1" });
  assert.equal(patched.path, "draft.md");
  assert.equal(fs.readFileSync(path.join(root, "draft.md"), "utf8"), "S1");

  // Phase D: move and soft-trash leave an approval-bound rollback manifest.
  const moved = await dispatch(workspace, "workspace.move", {
    from: "draft.md",
    to: "archive/draft.md",
  });
  const movedManifest = buildRollbackManifest({
    tool: "workspace.move",
    args: { from: "draft.md", to: "archive/draft.md" },
    result: moved,
    beforeStateHash: initial.hash,
  });
  assert.equal(movedManifest.action, "move_back");
  const trashed = await dispatch(workspace, "workspace.trash", { path: "archive/draft.md" });
  assert.equal(fs.existsSync(trashed.trash_path), true);
  assert.equal(buildRollbackManifest({
    tool: "workspace.trash",
    args: { path: "archive/draft.md" },
    result: trashed,
    beforeStateHash: initial.hash,
  }).action, "restore_from_trash");

  // Phase E: registered policy is bounded; unknown/Primary projects stay denied.
  assert.equal(evaluateProjectPolicy({ vaultRoot: root, projectId: "unknown", tool: "workspace.patch" }).code, "unknown_project");
  releaseLease({ storePath: path.join(state, "leases.json"), lease });
  assert.equal(created.path, "draft.md");
});
