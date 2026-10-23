import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const gateScript = path.resolve("services/inbox_executor/src/high_automation_gate.js");

function runGate(evidence) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "mcp-gate-"));
  fs.mkdirSync(path.join(root, "runtime", ".mcp-state"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "runtime", ".mcp-state", "high-automation-evidence.json"),
    JSON.stringify(evidence),
    "utf8",
  );
  return spawnSync(process.execPath, [gateScript], {
    cwd: root,
    env: { ...process.env, VAULT_WORKSPACE_ROOT: root },
    encoding: "utf8",
  });
}

const completeEvidence = {
  phases: Object.fromEntries(["A", "B", "C", "D", "E"].map((name) => [name, { status: "pass" }])),
  gates: Object.fromEntries([
    "lease_fencing",
    "state_hash",
    "append_only_journal",
    "cas_result_writeback",
    "primary_protection",
    "r3_baseline",
  ].map((name) => [name, "pass"])),
};

test("gate stays not ready until long-term and registered-project evidence exist", () => {
  const result = runGate(completeEvidence);
  assert.notEqual(result.status, 0);
  const output = JSON.parse(result.stdout);
  assert.equal(output.ready, false);
  assert.ok(output.reasons.includes("long_term_replay_not_passed"));
  assert.ok(output.reasons.includes("registered_projects_not_passed"));
});

test("gate becomes ready only when long-term and registered-project evidence pass", () => {
  const result = runGate({
    ...completeEvidence,
    long_term_replay: { status: "pass" },
    registered_projects: { status: "pass" },
  });
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(result.stdout);
  assert.equal(output.status, "MCP_HIGH_AUTOMATION_READY");
  assert.equal(output.ready, true);
});
