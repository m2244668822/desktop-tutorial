#!/usr/bin/env node
/**
 * Persist a deterministic router block for a queued contract with no
 * eligible executor. This never calls an LLM or an MCP write tool.
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { readInbox, setStatus, taskIdFromText, upsertNamedResult } from "./inbox.js";

const inboxPath = path.resolve(process.env.INBOX_PATH || "");
const expectedTaskId = String(process.env.BLOCKED_TASK_ID || "").trim();
const code = String(process.env.BLOCKED_CODE || "route_blocked").trim();
const reason = Buffer.from(String(process.env.BLOCKED_REASON_B64 || ""), "base64").toString("utf8").trim() || "not_routable";

if (!inboxPath || !fs.existsSync(inboxPath)) throw new Error("blocked_inbox_missing");
const current = readInbox(inboxPath);
if (current.status !== "queued") throw new Error(`blocked_status_changed:${current.status}`);
const taskId = taskIdFromText(current.text);
if (!taskId || taskId === "unknown" || (expectedTaskId && taskId !== expectedTaskId)) {
  throw new Error("blocked_task_identity_mismatch");
}

const traceId = crypto.randomUUID();
const result = [
  `- trace_id：\`${traceId}\``,
  `- task_id：\`${taskId}\``,
  `- 結果：blocked`,
  `- route：\`router\``,
  `- code：\`${code}\``,
  `- reason：${reason}`,
  `- auto_retry：false`,
  `- execution_started：false`,
  `- next_action：更新 executor 或 capacity 後建立新 contract 或人工重試`,
].join("\n");

const next = upsertNamedResult(setStatus(current.text, "blocked"), "## Result（router 回寫）", result);
const temporary = `${inboxPath}.router-block-${process.pid}-${Date.now()}.tmp`;
fs.writeFileSync(temporary, next, "utf8");
fs.renameSync(temporary, inboxPath);
process.stdout.write(JSON.stringify({ ok: true, task_id: taskId, status: "blocked", code, trace_id: traceId }) + "\n");
