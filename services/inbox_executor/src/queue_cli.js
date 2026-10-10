#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { VaultWorkspace } from "../../vault_workspace_mcp/src/workspace.js";
import { readInbox, resolveInboxPath, taskIdFromText } from "./inbox.js";
import { contractField, routeInboxTask } from "./executor_router.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);
const queueDir = path.resolve(
  vaultRoot,
  process.env.WHITE_STUDIO_TASK_QUEUE_DIR || path.join("智能體", "tasks")
);
const legacyInbox = process.env.INBOX_PATH
  ? path.resolve(process.env.INBOX_PATH)
  : resolveInboxPath(vaultRoot);

const PRIORITY = new Map([
  ["critical", 400],
  ["urgent", 400],
  ["high", 300],
  ["normal", 200],
  ["medium", 200],
  ["low", 100],
]);

function priorityOf(text) {
  const raw = String(contractField(text, "priority") || "normal").trim().toLowerCase();
  if (PRIORITY.has(raw)) return PRIORITY.get(raw);
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric : PRIORITY.get("normal");
}

function createdOf(text, filePath) {
  const frontmatter = String(text || "").match(/^---\s*\r?\n([\s\S]*?)\r?\n---/);
  const created = frontmatter?.[1]?.match(/^created:\s*(.+)$/mi)?.[1]?.trim() || "";
  const timestamp = created ? Date.parse(created) : Number.NaN;
  if (Number.isFinite(timestamp)) return timestamp;
  try {
    return fs.statSync(filePath).mtimeMs;
  } catch {
    return 0;
  }
}

function queuedFiles() {
  const files = [];
  if (fs.existsSync(queueDir)) {
    for (const name of fs.readdirSync(queueDir)) {
      if (!name.toLowerCase().endsWith(".md")) continue;
      const abs = path.join(queueDir, name);
      if (!fs.statSync(abs).isFile()) continue;
      files.push({ abs, source: "queue" });
    }
  }
  if (fs.existsSync(legacyInbox)) {
    files.push({ abs: legacyInbox, source: "legacy-inbox" });
  }
  return files;
}

function writeOutput(name, value) {
  if (!process.env.GITHUB_OUTPUT) return;
  fs.appendFileSync(process.env.GITHUB_OUTPUT, `${name}=${String(value)}\n`, "utf8");
}

const ws = new VaultWorkspace({
  workspaceRoot: vaultRoot,
  auditDir: path.join(vaultRoot, "runtime", ".mcp-audit"),
  trashDir: path.join(vaultRoot, "runtime", ".mcp-trash"),
  autoApprove: false,
});
const capabilities = ws.runtimeCapabilities();
const candidates = [];

for (const entry of queuedFiles()) {
  const current = readInbox(entry.abs);
  if (current.status !== "queued") continue;
  const taskId = taskIdFromText(current.text);
  if (!taskId) continue;
  const decision = routeInboxTask(current.text, capabilities, process.env);
  candidates.push({
    ...entry,
    taskId,
    text: current.text,
    decision,
    priority: priorityOf(current.text),
    created: createdOf(current.text, entry.abs),
  });
}

const runnable = candidates
  .filter((item) => item.decision.ok)
  .sort((a, b) =>
    (b.priority - a.priority) ||
    (a.created - b.created) ||
    a.taskId.localeCompare(b.taskId)
  );

if (runnable.length === 0) {
  const summary = {
    ok: false,
    code: candidates.length > 0 ? "queued_tasks_not_routable" : "queue_empty",
    queued_count: candidates.length,
    blocked: candidates.map((item) => ({
      task_id: item.taskId,
      code: item.decision.code,
      reason: item.decision.reason,
    })),
  };
  writeOutput("ok", "false");
  writeOutput("code", summary.code);
  writeOutput("queued_count", candidates.length);
  process.stdout.write(JSON.stringify(summary, null, 2) + "\n");
  process.exit(0);
}

const selected = runnable[0];
const relative = path.relative(vaultRoot, selected.abs).replace(/\\/g, "/");
const taskPathB64 = Buffer.from(relative, "utf8").toString("base64");
writeOutput("ok", "true");
writeOutput("code", "ok");
writeOutput("task_id", selected.taskId);
writeOutput("task_path_b64", taskPathB64);
writeOutput("route", selected.decision.route);
writeOutput("requested_executor", selected.decision.requested_executor || "");
writeOutput("selected_executor", selected.decision.selected_executor || "");
writeOutput("source", selected.source);
writeOutput("queued_count", candidates.length);

process.stdout.write(JSON.stringify({
  ok: true,
  task_id: selected.taskId,
  task_path: relative,
  source: selected.source,
  priority: selected.priority,
  route: selected.decision.route,
  requested_executor: selected.decision.requested_executor,
  selected_executor: selected.decision.selected_executor,
  reason: selected.decision.reason,
  scheduler: selected.decision.scheduler || { policy: "readiness-order-v1" },
  queued_count: candidates.length,
}, null, 2) + "\n");
