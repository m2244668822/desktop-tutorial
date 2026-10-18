#!/usr/bin/env node
/**
 * Path B inbox executor daemon.
 * Watches 智能體/chatgpt-inbox.md for status: queued.
 * Runs only ## Mechanical Actions JSON via vault_workspace_mcp.
 * Non-mechanical contracts are not executed here; the outer task router selects a headless coding executor.
 */

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import {
  VaultWorkspace,
  dispatch,
} from "../../vault_workspace_mcp/src/workspace.js";
import {
  readInbox,
  setStatus,
  classifyMechanicalActions,
  contractHash,
  taskIdFromText,
  upsertDaemonResult,
  resolveInboxPath,
} from "./inbox.js";
import { lookupAttempt, recordAttempt } from "./attempts.js";
import {
  executorIdentityFromEnvironment,
  executorIdentityMarkdown,
  upsertExecutorClaim,
  validateClaimResult,
} from "./executor_identity.js";
import {
  createOrchestratorStore,
  defaultOrchestratorStateRoot,
  newOperationContext,
} from "./orchestrator_store.js";
import { createAutonomyLease, defaultAutonomyRoot } from "./autonomy_lease.js";

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
const orchestratorStore = createOrchestratorStore(defaultOrchestratorStateRoot(vaultRoot));
const autonomyLease = createAutonomyLease({
  root: defaultAutonomyRoot(vaultRoot),
  owner: `inbox-daemon-${process.pid}`,
  ttlSeconds: Number(process.env.WHITE_STUDIO_AUTONOMY_LEASE_TTL || 1800),
});

const ALLOWED = new Set([
  "workspace.list",
  "workspace.search",
  "workspace.read",
  "workspace.create",
  "workspace.patch",
  "workspace.move",
  "workspace.trash",
  "runtime.capabilities",
  "runtime.run_test",
]);

let busy = false;
let leaseHeld = false;

function releaseLease() {
  busy = false;
  if (leaseHeld) {
    autonomyLease.release();
    leaseHeld = false;
  }
}

function log(msg) {
  process.stderr.write(`[inbox-executor] ${new Date().toISOString()} ${msg}\n`);
}

const recoveredStaleTasks = orchestratorStore.recoverStaleTasks({
  maxAgeSeconds: Number(process.env.WHITE_STUDIO_ORCHESTRATOR_STALE_SECONDS || 1800),
});
if (recoveredStaleTasks.length > 0) {
  log(`stale recovery blocked=${recoveredStaleTasks.length}`);
}

function failureClass(code, message, toolsFinished) {
  const permanent = new Set([
    "parse_error",
    "missing_actions",
    "approval_required",
    "approval_incomplete",
    "approval_expired",
    "tool_not_allowed",
    "done",
  ]);
  if (toolsFinished > 0) return { auto_retry: false, klass: "unknown_side_effect" };
  if (permanent.has(code)) return { auto_retry: false, klass: code };
  if (/timeout|timed out|econn|enotfound|network|fetch/i.test(`${code} ${message || ""}`)) {
    return { auto_retry: false, klass: "unknown_side_effect" };
  }
  return { auto_retry: false, klass: "needs-review" };
}

async function runContract() {
  if (busy) return;
  if (!fs.existsSync(inboxPath)) {
    log(`missing inbox: ${inboxPath}`);
    return;
  }

  const { text, status } = readInbox(inboxPath);
  if (status !== "queued") return;

  const taskId = taskIdFromText(text);
  const hash = contractHash(text);
  const prev = lookupAttempt(vaultRoot, taskId);
  if (
    prev &&
    prev.hash === hash &&
    prev.auto_retry === false &&
    !(prev.code === "executor_identity_invalid" && prev.identity_configuration_failure === true)
  ) {
    log(
      `retry_suppressed task_id=${taskId} trace_id=${prev.trace_id} code=${prev.code}`
    );
    const restoreStatus = prev.code === "done" ? "done" : "blocked";
    let restored = setStatus(text, restoreStatus);
    if (prev.result_markdown) {
      restored = upsertDaemonResult(restored, prev.result_markdown);
    }
    fs.writeFileSync(inboxPath, restored, "utf8");
    return;
  }

  if (!autonomyLease.acquire()) {
    log(`shared lease unavailable path=${autonomyLease.path}`);
    return;
  }
  leaseHeld = true;
  busy = true;
  let executorIdentity;
  try {
    executorIdentity = executorIdentityFromEnvironment(process.env);
  } catch (err) {
    const traceId = crypto.randomUUID();
    const code = err.code || "executor_identity_invalid";
    const resultMarkdown = `- trace_id：\`${traceId}\`\n- task_id：\`${taskId}\`\n- 時間：${new Date().toISOString()}\n- 結果：blocked\n- identity_validation：\`executor_identity_invalid\`\n- code：\`${code}\`\n- failure_class：\`needs-review\`\n- auto_retry：false\n- message：${err.message}`;
    let blocked = setStatus(text, "blocked");
    blocked = upsertDaemonResult(blocked, resultMarkdown);
    fs.writeFileSync(inboxPath, blocked, "utf8");
    recordAttempt(vaultRoot, taskId, {
      hash,
      code,
      failure_class: "needs-review",
      identity_configuration_failure: true,
      trace_id: traceId,
      auto_retry: false,
      pushed: false,
      writeback_pending: false,
      result_markdown: resultMarkdown,
    });
    log(`blocked: ${code} class=needs-review auto_retry=false trace_id=${traceId}`);
    releaseLease();
    return;
  }
  log(`detected queued → running executor_id=${executorIdentity.executor_id}`);
  let next = setStatus(text, "running");
  next = upsertExecutorClaim(next, taskId, executorIdentity);
  fs.writeFileSync(inboxPath, next, "utf8");

  const found = classifyMechanicalActions(next);
  const mechanical = found.ok ? found.parsed : null;

  const orchestration = newOperationContext(taskId, "inbox-daemon", hash);
  const writeTools = new Set([
    "workspace.create",
    "workspace.patch",
    "workspace.move",
    "workspace.trash",
  ]);
  const capability = mechanical?.actions?.some((step) => writeTools.has(step.tool))
    ? "disposable_write"
    : "read";
  orchestratorStore.create({
    ...orchestration,
    capability,
    mcp_server: "vault-workspace",
    tool_name: "mechanical-actions",
    contract_hash: hash,
  });
  orchestratorStore.transition(taskId, "running", {
    executor_id: executorIdentity.executor_id,
  });

  const traceId = crypto.randomUUID();
  log(`trace_id=${traceId} task_id=${taskId} parse=${found.code}`);

  if (!found.ok) {
    const code = found.code;
    const reason =
      code === "parse_error"
        ? `blocked: parse_error。Mechanical Actions JSON 無法解析（${found.message || "invalid"}）。同一 task_id 不再自動重跑。`
        : "blocked: 無 ## Mechanical Actions JSON。此 daemon 只執行機械契約；agentic 任務必須由外層 Executor Router 選擇 Codex/Cursor/VS Code handoff。";
    const identityValidation = validateClaimResult(next, taskId, executorIdentity);
    orchestratorStore.transition(taskId, "blocked", {
      validation_status: "failed",
      failure_code: code,
    });
    const resultMarkdown = `- trace_id：\`${traceId}\`\n- task_id：\`${taskId}\`\n- 時間：${new Date().toISOString()}\n- 結果：blocked\n${executorIdentityMarkdown(executorIdentity, identityValidation)}\n- code：\`${code}\`\n- message：${reason}`;
    next = setStatus(next, "blocked");
    next = upsertDaemonResult(next, resultMarkdown);
    fs.writeFileSync(inboxPath, next, "utf8");
    recordAttempt(vaultRoot, taskId, {
      hash,
      code,
      trace_id: traceId,
      auto_retry: false,
      pushed: false,
      writeback_pending: false,
      result_markdown: resultMarkdown,
      executor_identity: executorIdentity,
      identity_validation: identityValidation,
    });
    log(reason);
    releaseLease();
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

    orchestratorStore.transition(taskId, "validating", {
      validation_status: "pending",
      tool_count: results.length,
    });

    const identityValidation = validateClaimResult(
      fs.readFileSync(inboxPath, "utf8"),
      taskId,
      executorIdentity
    );
    if (!identityValidation.ok) {
      throw Object.assign(new Error(identityValidation.code), {
        code: identityValidation.code,
        identityValidation,
      });
    }
    const summary = results.map((r) => `- \`${r.tool}\` ok`).join("\n");
    const resultMarkdown = `- trace_id：\`${traceId}\`\n- task_id：\`${taskId}\`\n- 時間：${new Date().toISOString()}\n- 結果：done\n${executorIdentityMarkdown(executorIdentity, identityValidation)}\n- auto_approve：${autoApprove}\n- 動作：\n${summary}\n- 詳情：\n\`\`\`json\n${JSON.stringify(results, null, 2).slice(0, 4000)}\n\`\`\``;
    next = setStatus(fs.readFileSync(inboxPath, "utf8"), "done");
    next = upsertDaemonResult(next, resultMarkdown);
    fs.writeFileSync(inboxPath, next, "utf8");
    recordAttempt(vaultRoot, taskId, {
      hash,
      code: "done",
      trace_id: traceId,
      auto_retry: false,
      pushed: false,
      writeback_pending: false,
      result_markdown: resultMarkdown,
      executor_identity: executorIdentity,
      identity_validation: identityValidation,
    });
    orchestratorStore.transition(taskId, "done", {
      validation_status: "passed",
      result_code: "done",
    });
    log(`done trace_id=${traceId}`);
  } catch (err) {
    const code = err.code || "error";
    next = setStatus(fs.readFileSync(inboxPath, "utf8"), "blocked");
    const extra =
      err.proposed != null
        ? `\n- proposed：\n\`\`\`json\n${JSON.stringify(err.proposed, null, 2)}\n\`\`\``
        : "";
    const policy = failureClass(code, err.message, results.length);
    const currentTask = orchestratorStore.get(taskId);
    if (currentTask && !["done", "blocked", "failed"].includes(currentTask.status)) {
      orchestratorStore.transition(taskId, "blocked", {
        validation_status: "failed",
        failure_code: code,
      });
    }
    const identityValidation =
      err.identityValidation ||
      validateClaimResult(fs.readFileSync(inboxPath, "utf8"), taskId, executorIdentity);
    const resultMarkdown = `- trace_id：\`${traceId}\`\n- task_id：\`${taskId}\`\n- 時間：${new Date().toISOString()}\n- 結果：blocked\n${executorIdentityMarkdown(executorIdentity, identityValidation)}\n- code：\`${code}\`\n- failure_class：\`${policy.klass}\`\n- auto_retry：${policy.auto_retry}\n- message：${err.message}${extra}`;
    next = upsertDaemonResult(next, resultMarkdown);
    fs.writeFileSync(inboxPath, next, "utf8");
    recordAttempt(vaultRoot, taskId, {
      hash,
      code,
      failure_class: policy.klass,
      trace_id: traceId,
      auto_retry: policy.auto_retry,
      pushed: false,
      writeback_pending: false,
      result_markdown: resultMarkdown,
      executor_identity: executorIdentity,
      identity_validation: identityValidation,
    });
    log(
      `blocked: ${code} class=${policy.klass} auto_retry=${policy.auto_retry} trace_id=${traceId}`
    );
  } finally {
    releaseLease();
  }
}

async function tick() {
  try {
    await runContract();
  } catch (err) {
    log(`tick_error: ${err.message}`);
    releaseLease();
  }
}

log(`vault=${vaultRoot}`);
log(`inbox=${inboxPath}`);
log(`pollMs=${pollMs} once=${once} autoApproveEnv=${autoApproveEnv}`);

await tick();
if (once) process.exit(0);

setInterval(tick, pollMs);
