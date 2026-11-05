#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { processConversationEvent } from "./conversation_event.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);

function safeName(value, field) {
  const raw = String(value || "").trim();
  if (!raw) throw Object.assign(new Error(`invalid_${field}`), { code: `invalid_${field}` });
  const safe = raw.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 120);
  if (!safe) throw Object.assign(new Error(`invalid_${field}`), { code: `invalid_${field}` });
  return safe;
}

function inRoot(...parts) {
  const target = path.resolve(vaultRoot, ...parts);
  const rel = path.relative(vaultRoot, target);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw Object.assign(new Error("path_outside_vault"), { code: "path_outside_vault" });
  }
  return target;
}

function writeIdempotent(target, content) {
  if (fs.existsSync(target)) {
    const current = fs.readFileSync(target, "utf8");
    if (current === content) return { created: false, duplicate: true };
    throw Object.assign(new Error(`event_conflict:${path.basename(target)}`), {
      code: "event_conflict",
    });
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, content, "utf8");
  return { created: true, duplicate: false };
}

function taskMarkdown(processed) {
  const task = processed.event.proposals?.task;
  if (!task || typeof task !== "object" || Array.isArray(task)) return null;

  const taskId = safeName(task.task_id, "task_id");
  const route = String(task.route || "agentic").trim().toLowerCase();
  if (!["mechanical", "agentic"].includes(route)) {
    throw Object.assign(new Error("invalid_task_route"), { code: "invalid_task_route" });
  }

  const executor = String(task.executor || "auto").trim().toLowerCase();
  const goal = String(task.task_goal || "").trim();
  if (!goal) throw Object.assign(new Error("invalid_task_goal"), { code: "invalid_task_goal" });

  const project = String(task.project || "").trim();
  if (route === "agentic" && !project) {
    throw Object.assign(new Error("agentic_project_required"), {
      code: "agentic_project_required",
    });
  }

  const output = String(task.output || "implementation").trim();
  const priority = String(task.priority || "normal").trim();
  const eventPath = `智能體/conversation-events/${safeName(processed.event.event_id, "event_id")}.json`;

  const contractLines = [
    `task_id       ${taskId}`,
    `route         ${route}`,
    `executor      ${executor}`,
    project ? `project       ${project}` : null,
    `priority      ${priority}`,
    `Goal          ${goal.replace(/\r?\n/g, " ")}`,
    `Inputs        ${eventPath}`,
    "Safety        Treat user-model updates as candidates; do not promote to approved knowledge without explicit approval; no authority expansion; no destructive action by default.",
    `Output        ${output}`,
    "Done          Return exact evidence, remaining unknowns, and terminal state; claimed success without verification is UNVERIFIED.",
  ].filter(Boolean);

  let markdown = `---
status: queued
created: ${new Date().toISOString()}
type: conversation-event-task
source_event_id: ${processed.event.event_id}
---

## 現在這一份契約

\`\`\`text
${contractLines.join("\n")}
\`\`\`
`;

  if (route === "mechanical") {
    const actions = Array.isArray(task.mechanical_actions) ? task.mechanical_actions : [];
    if (actions.length === 0) {
      throw Object.assign(new Error("mechanical_actions_required"), {
        code: "mechanical_actions_required",
      });
    }
    markdown += `
## Mechanical Actions

\`\`\`json
${JSON.stringify(
  {
    executor: "inbox-daemon",
    auto_approve: Boolean(task.auto_approve),
    actions,
  },
  null,
  2
)}
\`\`\`
`;
  }
  return { taskId, markdown };
}

async function readInput() {
  const file = process.argv[2];
  if (file && !file.startsWith("--")) return fs.readFileSync(file, "utf8");
  let body = "";
  for await (const chunk of process.stdin) body += chunk;
  return body;
}

try {
  const raw = await readInput();
  const processed = processConversationEvent(JSON.parse(raw));

  const eventName = safeName(processed.event.event_id, "event_id");
  const eventTarget = inRoot("智能體", "conversation-events", `${eventName}.json`);
  const eventContent = JSON.stringify(processed, null, 2) + "\n";
  const eventWrite = writeIdempotent(eventTarget, eventContent);

  const task = taskMarkdown(processed);
  let queued = null;
  if (task) {
    const queueTarget = inRoot("智能體", "tasks", `${task.taskId}.md`);
    const queueWrite = writeIdempotent(queueTarget, task.markdown);
    queued = {
      task_id: task.taskId,
      path: path.relative(vaultRoot, queueTarget).replace(/\\/g, "/"),
      ...queueWrite,
    };
  }

  const digest = crypto.createHash("sha256").update(eventContent, "utf8").digest("hex");
  process.stdout.write(
    JSON.stringify(
      {
        ok: true,
        event_id: processed.event.event_id,
        event_path: path.relative(vaultRoot, eventTarget).replace(/\\/g, "/"),
        event_sha256: digest,
        event_created: eventWrite.created,
        duplicate: eventWrite.duplicate,
        queued,
        claim_candidates: processed.user_claim_candidates.length,
        permission_decisions: processed.permission_decisions.length,
      },
      null,
      2
    ) + "\n"
  );
} catch (error) {
  process.stderr.write(
    JSON.stringify({
      ok: false,
      code: error?.code || "conversation_enqueue_error",
      message: String(error?.message || error),
    }) + "\n"
  );
  process.exit(2);
}
