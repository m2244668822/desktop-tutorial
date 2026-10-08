#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { VaultWorkspace } from "../../vault_workspace_mcp/src/workspace.js";
import {
  readInbox,
  resolveInboxPath,
  setStatus,
  taskIdFromText,
  upsertNamedResult,
} from "./inbox.js";
import { routeInboxTask } from "./executor_router.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);
const inboxPath = process.env.INBOX_PATH || resolveInboxPath(vaultRoot);

function writeOutputs(decision) {
  if (!process.env.GITHUB_OUTPUT) return;
  fs.appendFileSync(
    process.env.GITHUB_OUTPUT,
    [
      `ok=${decision.ok ? "true" : "false"}`,
      `route=${decision.route || ""}`,
      `requested_executor=${decision.requested_executor || ""}`,
      `selected_executor=${decision.selected_executor || ""}`,
      `code=${decision.code || ""}`,
      `requires_ui=${decision.requires_ui ? "true" : "false"}`,
    ].join("\n") + "\n",
    "utf8"
  );
}

function persistBlocked(text, decision, message = "") {
  const taskId = taskIdFromText(text);
  const resultMarkdown = [
    `- task_id：\`${taskId}\``,
    "- 結果：blocked",
    "- executor_identity：未 claim",
    `- route：\`${decision.route || ""}\``,
    `- requested_executor：\`${decision.requested_executor || ""}\``,
    `- selected_executor：\`${decision.selected_executor || ""}\``,
    `- code：\`${decision.code || "router_blocked"}\``,
    `- requires_ui：${decision.requires_ui ? "true" : "false"}`,
    `- message：${message || decision.reason || "router_blocked"}`,
  ].join("\n");
  let blocked = setStatus(text, "blocked");
  blocked = upsertNamedResult(blocked, "## Result（task-router 回寫）", resultMarkdown);
  fs.writeFileSync(inboxPath, blocked, "utf8");
}

if (!fs.existsSync(inboxPath)) {
  const decision = {
    ok: false,
    route: "router",
    requested_executor: "",
    selected_executor: "",
    code: "inbox_missing",
    requires_ui: false,
  };
  writeOutputs(decision);
  process.stderr.write(`router: missing inbox ${inboxPath}\n`);
  process.exit(0);
}

const { text, status } = readInbox(inboxPath);
if (status !== "queued") {
  const decision = {
    ok: false,
    code: "inbox_not_queued",
    status,
    route: "idle",
    requested_executor: "",
    selected_executor: "",
    requires_ui: false,
  };
  writeOutputs(decision);
  process.stdout.write(JSON.stringify(decision));
  process.exit(0);
}

try {
  const ws = new VaultWorkspace({
    workspaceRoot: vaultRoot,
    auditDir: path.join(vaultRoot, "runtime", ".mcp-audit"),
    trashDir: path.join(vaultRoot, "runtime", ".mcp-trash"),
    autoApprove: false,
  });
  const capabilities = ws.runtimeCapabilities();
  const decision = routeInboxTask(text, capabilities, process.env);

  if (!decision.ok) {
    persistBlocked(text, decision);
  }

  writeOutputs(decision);
  process.stdout.write(JSON.stringify({ ...decision, capabilities }, null, 2));
  process.exit(0);
} catch (error) {
  const decision = {
    ok: false,
    route: "router",
    requested_executor: "",
    selected_executor: "",
    reason: "router_exception",
    code: "router_exception",
    headless: true,
    requires_ui: false,
  };
  const message = String(error?.stack || error?.message || error)
    .replace(/\r?\n/g, " ")
    .slice(0, 1500);
  try {
    persistBlocked(text, decision, message);
  } catch (persistError) {
    process.stderr.write(
      `router: failed to persist exception result: ${String(
        persistError?.stack || persistError
      )}\n`
    );
  }
  writeOutputs(decision);
  process.stderr.write(`router_exception: ${message}\n`);
  process.exit(0);
}
