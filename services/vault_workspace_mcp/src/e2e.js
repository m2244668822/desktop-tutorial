#!/usr/bin/env node
/**
 * L1 E2E: read → propose patch → checkpoint → patch → verify → rollback
 * Isolated git repo under runtime/.mcp-e2e-scratch (does not commit the vault).
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { VaultWorkspace } from "./workspace.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(__dirname, "..", "..", "..", "..");
const scratchRoot = path.join(vaultRoot, "runtime", ".mcp-e2e-scratch");
const auditDir = path.join(scratchRoot, ".mcp-audit");
const trashDir = path.join(scratchRoot, ".mcp-trash");

fs.rmSync(scratchRoot, { recursive: true, force: true });
fs.mkdirSync(scratchRoot, { recursive: true });

function git(args) {
  const r = spawnSync("git", args, { cwd: scratchRoot, encoding: "utf8" });
  if (r.status !== 0) throw new Error(`git ${args.join(" ")} failed: ${r.stderr}`);
  return r.stdout.trim();
}

git(["init"]);
git(["config", "user.email", "mcp-e2e@local"]);
git(["config", "user.name", "mcp-e2e"]);

const relFile = "e2e-target.md";
fs.writeFileSync(path.join(scratchRoot, relFile), "# e2e before\n", "utf8");
git(["add", "-A"]);
git(["commit", "-m", "e2e-seed"]);

const ws = new VaultWorkspace({
  workspaceRoot: scratchRoot,
  auditDir,
  trashDir,
  autoApprove: true,
});

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const read1 = await ws.read({ path: relFile });
assert(read1.content.includes("e2e before"), "read failed");

const proposed = await ws.proposePatch({
  path: relFile,
  content: "# e2e after\n",
});
assert(proposed.diff_hash, "missing diff_hash");
console.log("diff_hash", proposed.diff_hash);

const checkpoint = ws.gitCheckpoint({ message: "mcp-e2e-checkpoint-before-patch" });
assert(checkpoint.rollback_id, "missing rollback_id");
console.log("rollback_id", checkpoint.rollback_id);

const patched = await ws.patch({
  path: relFile,
  content: "# e2e after\n",
  approval: {
    approved: true,
    action_id: proposed.action_id,
    diff_hash: proposed.diff_hash,
    expires_at: new Date(Date.now() + 600_000).toISOString(),
  },
});
assert(patched.hash === proposed.after_hash, "hash mismatch after patch");

const read2 = await ws.read({ path: relFile });
assert(read2.content.includes("e2e after"), "patch not applied");

const rolled = await ws.rollbackTo({ rollback_id: checkpoint.rollback_id });
assert(rolled.rollback_id === checkpoint.rollback_id, "rollback id mismatch");

const read3 = await ws.read({ path: relFile });
assert(read3.content.includes("e2e before"), "rollback did not restore content");

const auditPath = path.join(auditDir, "mcp-audit.jsonl");
assert(fs.existsSync(auditPath), "audit log missing");
const last = fs.readFileSync(auditPath, "utf8").trim().split("\n").pop();
console.log("audit_last", last);
console.log("E2E_PASS");
