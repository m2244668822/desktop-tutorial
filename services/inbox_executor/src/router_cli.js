#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { VaultWorkspace } from "../../vault_workspace_mcp/src/workspace.js";
import { readInbox, resolveInboxPath, setStatus, taskIdFromText, upsertNamedResult } from "./inbox.js";
import { routeInboxTask } from "./executor_router.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);
const inboxPath = process.env.INBOX_PATH || resolveInboxPath(vaultRoot);

if (!fs.existsSync(inboxPath)) {
  process.stderr.write(`router: missing inbox ${inboxPath}\n`);
  process.exit(2);
}

const { text, status } = readInbox(inboxPath);
if (status !== "queued") {
  const out = {
    ok: false,
    code: "inbox_not_queued",
    status,
    route: "idle",
    requested_executor: "",
    selected_executor: "",
    requires_ui: false,
  };
  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(
      process.env.GITHUB_OUTPUT,
      [
        "ok=false",
        "route=idle",
        "requested_executor=",
        "selected_executor=",
        "code=inbox_not_queued",
        "requires_ui=false",
      ].join("\n") + "\n",
      "utf8"
    );
  }
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
}

const ws = new VaultWorkspace({
  workspaceRoot: vaultRoot,
  auditDir: path.join(vaultRoot, "runtime", ".mcp-audit"),
  trashDir: path.join(vaultRoot, "runtime", ".mcp-trash"),
  autoApprove: false,
});
const capabilities = ws.runtimeCapabilities();
const decision = routeInboxTask(text, capabilities, process.env);

if (!decision.ok) {
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
    `- message：${decision.reason || "router_blocked"}`,
  ].join("\n");
  let blocked = setStatus(text, "blocked");
  blocked = upsertNamedResult(blocked, "## Result（task-router 回寫）", resultMarkdown);
  fs.writeFileSync(inboxPath, blocked, "utf8");
}

if (process.env.GITHUB_OUTPUT) {
  const lines = [
    `ok=${decision.ok ? "true" : "false"}`,
    `route=${decision.route || ""}`,
    `requested_executor=${decision.requested_executor || ""}`,
    `selected_executor=${decision.selected_executor || ""}`,
    `code=${decision.code || ""}`,
    `requires_ui=${decision.requires_ui ? "true" : "false"}`,
  ];
  fs.appendFileSync(process.env.GITHUB_OUTPUT, lines.join("\n") + "\n", "utf8");
}

process.stdout.write(JSON.stringify({ ...decision, capabilities }, null, 2));
process.exit(0);
