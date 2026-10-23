#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(here, "..", "..", "..", "..")
);
const evidencePath = path.join(
  vaultRoot,
  process.env.WHITE_STUDIO_HIGH_AUTOMATION_EVIDENCE ||
    path.join("runtime", ".mcp-state", "high-automation-evidence.json")
);
const phases = ["A", "B", "C", "D", "E"];
const reasons = [];
let evidence = null;

try {
  evidence = JSON.parse(fs.readFileSync(evidencePath, "utf8"));
} catch {
  reasons.push("phase_evidence_missing");
}

for (const phase of phases) {
  if (evidence?.phases?.[phase]?.status !== "pass") {
    reasons.push("phase_" + phase + "_not_passed");
  }
}

for (const item of [
  "lease_fencing",
  "state_hash",
  "append_only_journal",
  "cas_result_writeback",
  "primary_protection",
  "r3_baseline",
]) {
  if (evidence?.gates?.[item] !== "pass") reasons.push(item + "_not_passed");
}

// A single disposable run is not long-term unattended evidence. Registered
// projects must also have their own Phase B-E evidence before the final gate.
if (evidence?.long_term_replay?.status !== "pass") reasons.push("long_term_replay_not_passed");
if (evidence?.registered_projects?.status !== "pass") reasons.push("registered_projects_not_passed");

const ready = reasons.length === 0;
const output = {
  status: ready ? "MCP_HIGH_AUTOMATION_READY" : "MCP_HIGH_AUTOMATION_NOT_READY",
  ready,
  evidence_path: path.relative(vaultRoot, evidencePath).replace(/\\/g, "/"),
  reasons,
};
process.stdout.write(JSON.stringify(output, null, 2) + "\n");
process.exit(ready ? 0 : 1);
