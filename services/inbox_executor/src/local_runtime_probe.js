#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { VaultWorkspace } from "../../vault_workspace_mcp/src/workspace.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);

function git(args) {
  const r = spawnSync("git", args, { cwd: vaultRoot, encoding: "utf8", timeout: 10000 });
  return {
    ok: r.status === 0 && !r.error,
    status: r.status,
    stdout: String(r.stdout || "").trim().slice(0, 3000),
    stderr: String(r.stderr || "").trim().slice(0, 1000),
  };
}

const ws = new VaultWorkspace({
  workspaceRoot: vaultRoot,
  auditDir: path.join(vaultRoot, "runtime", ".mcp-audit"),
  trashDir: path.join(vaultRoot, "runtime", ".mcp-trash"),
  autoApprove: false,
});
const capabilities = ws.runtimeCapabilities();
const queueDir = path.join(vaultRoot, "智能體", "tasks");
const eventDir = path.join(vaultRoot, "智能體", "conversation-events");
const queued = fs.existsSync(queueDir)
  ? fs.readdirSync(queueDir).filter((name) => name.toLowerCase().endsWith(".md")).length
  : 0;

const result = {
  ok: true,
  checked_at: new Date().toISOString(),
  vault_root: vaultRoot,
  platform: capabilities.platform,
  git: {
    status: git(["status", "--short"]),
    head: git(["rev-parse", "HEAD"]),
    branch: git(["branch", "--show-current"]),
    remote: git(["remote", "get-url", "origin"]),
  },
  runtime: capabilities,
  queue: {
    path: queueDir,
    exists: fs.existsSync(queueDir),
    task_files: queued,
  },
  conversation_events: {
    path: eventDir,
    exists: fs.existsSync(eventDir),
  },
  blockers: [],
};

if (capabilities.platform !== "win32") result.blockers.push("not_windows");
if (!capabilities.commands.node) result.blockers.push("node_unavailable");
if (!capabilities.executors.workspace_mcp) result.blockers.push("workspace_mcp_unavailable");
if (
  !capabilities.executor_readiness.codex.headless_ready &&
  !capabilities.executor_readiness.cursor.headless_ready
) {
  result.blockers.push("no_headless_agentic_executor_ready");
}

process.stdout.write(JSON.stringify(result, null, 2) + "\n");
