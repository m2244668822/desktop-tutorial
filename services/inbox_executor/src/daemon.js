#!/usr/bin/env node
/**
 * Path B inbox executor daemon.
 * Watches 智能體/chatgpt-inbox.md for status: queued.
 * Runs only ## Mechanical Actions JSON via vault_workspace_mcp.
 * Non-mechanical contracts → blocked (hand off to Cursor).
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  VaultWorkspace,
  dispatch,
} from "../../vault_workspace_mcp/src/workspace.js";
import {
  readInbox,
  setStatus,
  extractMechanicalActions,
  upsertDaemonResult,
  resolveInboxPath,
} from "./inbox.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);
const inboxPath = process.env.INBOX_PATH || resolveInboxPath(vaultRoot);
const pollMs = Number(process.env.INBOX_POLL_MS || 5000);
const once = process.argv.includes("--once");
const autoApproveEnv = process.env.INBOX_AUTO_APPROVE === "1";

const auditDir = path.join(vaultRoot, "runtime", ".mcp-audit");
const trashDir = path.join(vaultRoot, "runtime", ".mcp-trash");

const ALLOWED = new Set([
  "workspace.list",
  "workspace.search",
  "workspace.read",
  "workspace.create",
  "workspace.patch",
  "workspace.move",
  "workspace.trash",
  "git.checkpoint",
]);

let busy = false;

function log(msg) {
  process.stderr.write(`[inbox-executor] ${new Date().toISOString()} ${msg}\n`);
}

async function runContract() {
  if (busy) return;
  if (!fs.existsSync(inboxPath)) {
    log(`missing inbox: ${inboxPath}`);
    return;
  }

  const { text, status } = readInbox(inboxPath);
  if (status !== "queued") return;

  busy = true;
  log("detected queued → running");
  let next = setStatus(text, "running");
  fs.writeFileSync(inboxPath, next, "utf8");

  const mechanical = extractMechanicalActions(next);
  if (!mechanical) {
    const reason =
      "blocked: 無 ## Mechanical Actions JSON。非機械契約請用 Cursor「跑 inbox」，或請 ChatGPT 補機械動作區塊。";
    next = setStatus(next, "blocked");
    next = upsertDaemonResult(
      next,
      `- 時間：${new Date().toISOString()}\n- 結果：\`${reason}\`\n- 下一步：補機械動作，或改由 Cursor 執行`
    );
    fs.writeFileSync(inboxPath, next, "utf8");
    log(reason);
    busy = false;
    return;
  }

  const autoApprove = Boolean(mechanical.auto_approve) || autoApproveEnv;
  const ws = new VaultWorkspace({
    workspaceRoot: vaultRoot,
    auditDir,
    trashDir,
    autoApprove,
  });

  const results = [];
  try {
    for (const step of mechanical.actions) {
      const tool = step.tool;
      const args = step.args || {};
      if (!ALLOWED.has(tool)) {
        throw Object.assign(new Error(`tool_not_allowed:${tool}`), {
          code: "tool_not_allowed",
        });
      }
      // L2+ without auto_approve needs approval object on write tools
      if (
        !autoApprove &&
        ["workspace.create", "workspace.patch", "workspace.move", "workspace.trash"].includes(
          tool
        )
      ) {
        if (!args.approval || args.approval.approved !== true) {
          // propose-only for patch if content given: attach required approval shape hint
          if (tool === "workspace.patch" && args.path && args.content != null) {
            const proposed = await ws.proposePatch({
              path: args.path,
              content: args.content,
            });
            throw Object.assign(
              new Error(
                `approval_required:diff_hash=${proposed.diff_hash};action_id=${proposed.action_id}`
              ),
              { code: "approval_required", proposed }
            );
          }
          throw Object.assign(new Error("approval_required"), {
            code: "approval_required",
          });
        }
      }
      const out = await dispatch(ws, tool, args);
      const slim =
        out && typeof out === "object"
          ? {
              ...out,
              content:
                typeof out.content === "string"
                  ? `${out.content.slice(0, 200)}…(truncated)`
                  : out.content,
            }
          : out;
      results.push({ tool, ok: true, out: slim });
    }

    const summary = results
      .map((r) => `- \`${r.tool}\` ok`)
      .join("\n");
    next = setStatus(fs.readFileSync(inboxPath, "utf8"), "done");
    next = upsertDaemonResult(
      next,
      `- 時間：${new Date().toISOString()}\n- 結果：done\n- auto_approve：${autoApprove}\n- 動作：\n${summary}\n- 詳情：\n\`\`\`json\n${JSON.stringify(results, null, 2).slice(0, 4000)}\n\`\`\``
    );
    fs.writeFileSync(inboxPath, next, "utf8");
    log("done");
  } catch (err) {
    const code = err.code || "error";
    next = setStatus(fs.readFileSync(inboxPath, "utf8"), "blocked");
    const extra =
      err.proposed != null
        ? `\n- proposed：\n\`\`\`json\n${JSON.stringify(err.proposed, null, 2)}\n\`\`\``
        : "";
    next = upsertDaemonResult(
      next,
      `- 時間：${new Date().toISOString()}\n- 結果：blocked\n- code：\`${code}\`\n- message：${err.message}${extra}\n- 提示：設 actions[].args.approval 或 mechanical.auto_approve=true／環境變數 INBOX_AUTO_APPROVE=1（僅信任契約時）`
    );
    fs.writeFileSync(inboxPath, next, "utf8");
    log(`blocked: ${code} ${err.message}`);
  } finally {
    busy = false;
  }
}

async function tick() {
  try {
    await runContract();
  } catch (err) {
    log(`tick_error: ${err.message}`);
    busy = false;
  }
}

log(`vault=${vaultRoot}`);
log(`inbox=${inboxPath}`);
log(`pollMs=${pollMs} once=${once} autoApproveEnv=${autoApproveEnv}`);

await tick();
if (once) process.exit(0);

setInterval(tick, pollMs);
