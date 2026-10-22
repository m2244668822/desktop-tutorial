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
import { contractField } from "./executor_router.js";
import {
  acquireLease,
  appendJournalTransition,
  assertLeaseFence,
  captureWorkspaceState,
  buildRollbackManifest,
  evaluateProjectPolicy,
  gitBlobRevision,
  idempotencyDecision,
  readJournal,
  releaseLease,
  sha256,
  stableJson,
  validateResultWriteback,
} from "./transaction.js";

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
const stateDir = path.join(vaultRoot, "runtime", ".mcp-state");
const leasePath = path.join(stateDir, "leases.json");
const journalPath = path.join(stateDir, "operations.jsonl");

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

function log(msg) {
  process.stderr.write(`[inbox-executor] ${new Date().toISOString()} ${msg}\n`);
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
    busy = false;
    return;
  }
  let lease;
  try {
    lease = acquireLease({
      storePath: leasePath,
      taskId,
      executorId: executorIdentity.executor_id,
      ttlMs: Number(process.env.INBOX_LEASE_TTL_MS || 30000),
    });
  } catch (err) {
    log(`blocked: ${err.code || "lease_acquire_failed"} task_id=${taskId}`);
    busy = false;
    return;
  }
  const runId = crypto.randomUUID();
  const remoteTaskRevision = gitBlobRevision(
    vaultRoot,
    path.relative(vaultRoot, inboxPath),
    hash
  );
  log(`detected queued → running executor_id=${executorIdentity.executor_id}`);
  let next = setStatus(text, "running");
  next = upsertExecutorClaim(next, taskId, executorIdentity);
  fs.writeFileSync(inboxPath, next, "utf8");

  const found = classifyMechanicalActions(next);
  const mechanical = found.ok ? found.parsed : null;
  const traceId = crypto.randomUUID();
  log(`trace_id=${traceId} task_id=${taskId} parse=${found.code}`);

  if (!found.ok) {
    const code = found.code;
    const reason =
      code === "parse_error"
        ? `blocked: parse_error。Mechanical Actions JSON 無法解析（${found.message || "invalid"}）。同一 task_id 不再自動重跑。`
        : "blocked: 無 ## Mechanical Actions JSON。此 daemon 只執行機械契約；agentic 任務必須由外層 Executor Router 選擇 Codex/Cursor/VS Code handoff。";
    const identityValidation = validateClaimResult(next, taskId, executorIdentity);
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
    releaseLease({ storePath: leasePath, lease });
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
    for (const [index, step] of mechanical.actions.entries()) {
      const tool = step.tool;
      const args = step.args || {};
      if (!ALLOWED.has(tool)) {
        throw Object.assign(new Error(`tool_not_allowed:${tool}`), {
          code: "tool_not_allowed",
        });
      }
      assertLeaseFence({ storePath: leasePath, lease });
      const projectId = contractField(text, "project") || "obsidian-vault-refactor-2026-09-08";
      const policy = evaluateProjectPolicy({
        vaultRoot,
        projectId,
        tool,
        targetPath: args.path || args.source || args.destination || "",
      });
      if (!policy.ok) {
        throw Object.assign(new Error(policy.code), { code: policy.code });
      }
      const operationRequest = { task_id: taskId, tool, args };
      const requestHash = sha256(stableJson(operationRequest));
      const idempotencyKey = sha256(`${taskId}:${hash}:${index}:${tool}`);
      const operationId = `op-${idempotencyKey.slice(0, 24)}`;
      const stateBefore = captureWorkspaceState({
        projectRoot: vaultRoot,
        projectId,
        policyScope: policy.policyScope,
        normalizedRoot: policy.projectRoot || projectId,
        targetPaths: [args.path, args.source, args.destination].filter(Boolean),
      });
      const journalBase = {
        operation_id: operationId,
        task_id: taskId,
        run_id: runId,
        lease_id: lease.lease_id,
        lease_generation: lease.lease_generation,
        fencing_token: lease.fencing_token,
        timestamp: new Date().toISOString(),
        executor_id: executorIdentity.executor_id,
        state_hash: stateBefore.hash,
        request_hash: requestHash,
        idempotency_key: idempotencyKey,
        evidence_ref: path.relative(vaultRoot, journalPath).replace(/\\/g, "/"),
        error_code: "",
      };
      const decision = idempotencyDecision(readJournal(journalPath), idempotencyKey, requestHash);
      if (decision.action === "deny") {
        throw Object.assign(new Error("HARD_CONFLICT"), { code: "HARD_CONFLICT" });
      }
      appendJournalTransition(journalPath, { ...journalBase, transition: "requested" });
      if (decision.action === "replay") {
        results.push({ tool, ok: true, replay: true, out: decision.result });
        continue;
      }
      appendJournalTransition(journalPath, { ...journalBase, transition: "authorized" });
      assertLeaseFence({ storePath: leasePath, lease });
      appendJournalTransition(journalPath, { ...journalBase, transition: "executing" });
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
      assertLeaseFence({ storePath: leasePath, lease });
      const stateAfter = captureWorkspaceState({
        projectRoot: vaultRoot,
        projectId,
        policyScope: policy.policyScope,
        normalizedRoot: policy.projectRoot || projectId,
        targetPaths: [args.path, args.source, args.destination].filter(Boolean),
      });
      const rollbackManifest = buildRollbackManifest({
        tool,
        args,
        result: out,
        beforeStateHash: stateBefore.hash,
      });
      appendJournalTransition(journalPath, {
        ...journalBase,
        transition: "applied",
        state_hash: stateAfter.hash,
        result: out,
        rollback_manifest: rollbackManifest,
      });
      appendJournalTransition(journalPath, {
        ...journalBase,
        transition: "validated",
        state_hash: stateAfter.hash,
      });
      appendJournalTransition(journalPath, {
        ...journalBase,
        transition: "completed",
        state_hash: stateAfter.hash,
        result: out,
        rollback_manifest: rollbackManifest,
      });
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

    assertLeaseFence({ storePath: leasePath, lease });
    const currentText = fs.readFileSync(inboxPath, "utf8");
    const currentRevision = gitBlobRevision(
      vaultRoot,
      path.relative(vaultRoot, inboxPath),
      contractHash(currentText)
    );
    const writebackCheck = validateResultWriteback({
      taskId,
      expectedTaskId: taskId,
      lease,
      expectedLease: lease,
      remoteTaskRevision: currentRevision,
      expectedRemoteTaskRevision: remoteTaskRevision,
      remoteStatus: "queued",
    });
    if (!writebackCheck.ok) {
      throw Object.assign(new Error("stale_task_revision"), { code: "stale_task_revision" });
    }
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
    const resultMarkdown = `- trace_id：\`${traceId}\`\n- task_id：\`${taskId}\`\n- run_id：\`${runId}\`\n- lease_id：\`${lease.lease_id}\`\n- lease_generation：${lease.lease_generation}\n- fencing_token：\`${lease.fencing_token}\`\n- remote_task_revision：\`${remoteTaskRevision}\`\n- 時間：${new Date().toISOString()}\n- 結果：done\n${executorIdentityMarkdown(executorIdentity, identityValidation)}\n- auto_approve：${autoApprove}\n- 動作：\n${summary}\n- 詳情：\n\`\`\`json\n${JSON.stringify(results, null, 2).slice(0, 4000)}\n\`\`\``;
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
    log(`done trace_id=${traceId}`);
    releaseLease({ storePath: leasePath, lease });
  } catch (err) {
    const code = err.code || "error";
    if (!['stale_lease', 'lease_expired', 'stale_fencing_token'].includes(code)) {
      const failedStep = mechanical.actions[results.length] || {};
      const failedRequestHash = sha256(stableJson({ task_id: taskId, tool: failedStep.tool || "unknown", args: failedStep.args || {} }));
      try {
        appendJournalTransition(journalPath, {
          operation_id: "op-failed-" + sha256(taskId + ":" + results.length).slice(0, 20),
          task_id: taskId,
          run_id: runId,
          lease_id: lease.lease_id,
          lease_generation: lease.lease_generation,
          fencing_token: lease.fencing_token,
          timestamp: new Date().toISOString(),
          executor_id: executorIdentity.executor_id,
          state_hash: "unknown",
          request_hash: failedRequestHash,
          idempotency_key: sha256(taskId + ":failed:" + results.length),
          evidence_ref: path.relative(vaultRoot, journalPath).replace(/\\/g, "/"),
          error_code: code,
          transition: code === "approval_required" ? "blocked" : "failed",
        });
      } catch (journalError) {
        log(`journal_failure code=${journalError.code || journalError.message}`);
      }
    }
    try {
      assertLeaseFence({ storePath: leasePath, lease });
    } catch (fenceError) {
      log(`result_not_published task_id=${taskId} code=${fenceError.code}`);
      releaseLease({ storePath: leasePath, lease });
      busy = false;
      return;
    }
    next = setStatus(fs.readFileSync(inboxPath, "utf8"), "blocked");
    const extra =
      err.proposed != null
        ? `\n- proposed：\n\`\`\`json\n${JSON.stringify(err.proposed, null, 2)}\n\`\`\``
        : "";
    const policy = failureClass(code, err.message, results.length);
    const identityValidation =
      err.identityValidation ||
      validateClaimResult(fs.readFileSync(inboxPath, "utf8"), taskId, executorIdentity);
    const resultMarkdown = `- trace_id：\`${traceId}\`\n- task_id：\`${taskId}\`\n- run_id：\`${runId}\`\n- lease_id：\`${lease.lease_id}\`\n- lease_generation：${lease.lease_generation}\n- fencing_token：\`${lease.fencing_token}\`\n- remote_task_revision：\`${remoteTaskRevision}\`\n- 時間：${new Date().toISOString()}\n- 結果：blocked\n${executorIdentityMarkdown(executorIdentity, identityValidation)}\n- code：\`${code}\`\n- failure_class：\`${policy.klass}\`\n- auto_retry：${policy.auto_retry}\n- message：${err.message}${extra}`;
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
    releaseLease({ storePath: leasePath, lease });
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
