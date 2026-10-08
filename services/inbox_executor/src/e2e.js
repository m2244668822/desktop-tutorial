import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  executorIdentityFromEnvironment,
  extractExecutorClaim,
  extractExecutorResultIdentity,
  normalizeExecutorIdentity,
  upsertExecutorClaim,
  validateClaimResult,
  validateExecutorIdentityMatch,
  validatePersistedClaimResult,
} from "./executor_identity.js";
import { classifyMechanicalActions, contractHash, currentTaskEnvelope, taskIdFromText, upsertDaemonResult } from "./inbox.js";
import { contractField, routeInboxTask } from "./executor_router.js";

const claimedAt = "2026-09-30T00:00:00.000Z";
const codex = normalizeExecutorIdentity({
  executor_id: "codex",
  executor_type: "external",
  executor_provider: "openai",
  executor_product: "codex",
  executor_mode: "desktop",
  executor_version: "declared-current",
  executor_capabilities: ["workspace-mcp", "bounded-tests"],
  claimed_at: claimedAt,
});

const taskId = "angel-executor-identity-contract-20260930";

const readyCaps = {
  executor_readiness: {
    codex: { installed: true, authenticated: true, headless_ready: true },
    cursor: { installed: true, authenticated: true, headless_ready: true },
    vscode: { installed: true, interactive_only: true, headless_ready: false },
  },
};
const agenticAuto = `task_id       route-test
route         agentic
executor      auto
project       desktop-tutorial
Goal          fix the failing test
`;
assert.equal(contractField(agenticAuto, "executor"), "auto");
assert.deepEqual(
  routeInboxTask(agenticAuto, readyCaps, { WHITE_STUDIO_EXECUTOR_ORDER: "codex,cursor" }),
  {
    ok: true,
    route: "agentic",
    requested_executor: "auto",
    selected_executor: "codex",
    reason: "auto_selected_codex",
    code: "ok",
    headless: true,
    requires_ui: false,
  }
);
assert.equal(
  routeInboxTask(agenticAuto, {
    executor_readiness: {
      codex: { installed: true, authenticated: false, headless_ready: false },
      cursor: { installed: true, authenticated: true, headless_ready: true },
    },
  }).selected_executor,
  "cursor"
);
assert.equal(
  routeInboxTask(agenticAuto.replace("executor      auto", "executor      vscode"), readyCaps).code,
  "interactive_executor_required"
);
assert.equal(
  routeInboxTask(agenticAuto, { executor_readiness: {} }).code,
  "executor_unavailable"
);
assert.equal(
  routeInboxTask(agenticAuto.replace("project       desktop-tutorial\n", ""), readyCaps).code,
  "project_required"
);
assert.equal(
  routeInboxTask(agenticAuto.replace("executor      auto", "executor      codxe"), readyCaps).code,
  "invalid_executor"
);

const queued = `---\nstatus: queued\n---\n\ntask_id       ${taskId}\n\n## Result\n`;
const mechanicalRouteText = `task_id       mechanical-route
route         mechanical
executor      auto

## Mechanical Actions

\`\`\`json
{"actions":[{"tool":"workspace.read","args":{"path":"README.md"}}]}
\`\`\`
`;
assert.equal(routeInboxTask(mechanicalRouteText, readyCaps).selected_executor, "inbox-daemon");
assert.equal(routeInboxTask(mechanicalRouteText, readyCaps).route, "mechanical");

const longLivedInbox = `---
status: queued
---

## 過去任務

task_id       old-task
route         mechanical
executor      cursor
project       old-project

## Mechanical Actions

\`\`\`json
{"actions":[{"tool":"workspace.read","args":{"path":"old.md"}}]}
\`\`\`

## 現在這一份契約

task_id       current-task
route         agentic
executor      codex
project       desktop-tutorial
Goal          fix current task only

## Result（old 回寫）

- task_id：\`old-task\`

## 待排入

task_id       future-task
executor      vscode
`;
assert.equal(taskIdFromText(longLivedInbox), "current-task");
assert.equal(contractField(longLivedInbox, "executor"), "codex");
assert.equal(contractField(longLivedInbox, "project"), "desktop-tutorial");
assert.equal(routeInboxTask(longLivedInbox, readyCaps).route, "agentic");
assert.equal(routeInboxTask(longLivedInbox, readyCaps).selected_executor, "codex");
assert.equal(classifyMechanicalActions(longLivedInbox).ok, false);
assert.match(currentTaskEnvelope(longLivedInbox), /task_id       current-task/);
assert.doesNotMatch(currentTaskEnvelope(longLivedInbox), /old-task/);
assert.doesNotMatch(currentTaskEnvelope(longLivedInbox), /future-task/);

const longLivedMechanicalInbox = longLivedInbox.replace(
  `route         agentic
executor      codex
project       desktop-tutorial
Goal          fix current task only`,
  `route         mechanical
executor      auto
project       desktop-tutorial
Goal          read current README

## Mechanical Actions

\`\`\`json
{"actions":[{"tool":"workspace.read","args":{"path":"README.md"}}]}
\`\`\``
);
assert.equal(classifyMechanicalActions(longLivedMechanicalInbox).ok, true);
assert.equal(
  routeInboxTask(longLivedMechanicalInbox, readyCaps).selected_executor,
  "inbox-daemon"
);
const running = upsertExecutorClaim(queued, taskId, codex);
const claim = extractExecutorClaim(running);
assert.equal(claim.legacy, false);
assert.deepEqual(claim.identity, codex);
assert.deepEqual(validateClaimResult(running, taskId, codex), {
  ok: true,
  code: "executor_identity_match",
  legacy: false,
  mismatches: [],
});

const fencedClaimExamples = `---\nstatus: queued\n---\n\n\`\`\`md\n## Executor Claim\n\n- task_id：\`example-claim\`\n\`\`\`\n\n~~~md\n## Result\n\n- task_id：\`example-result\`\n~~~\n`;
const claimOutsideExamples = upsertExecutorClaim(fencedClaimExamples, taskId, codex);
assert.deepEqual(extractExecutorClaim(claimOutsideExamples).identity, codex);
assert.match(claimOutsideExamples, /- task_id：`example-claim`/);
assert.match(claimOutsideExamples, /- task_id：`example-result`/);
assert.equal((claimOutsideExamples.match(/^## Executor Claim$/gm) || []).length, 2);

const replacedClaim = upsertExecutorClaim(running, taskId, codex);
assert.doesNotMatch(replacedClaim, /```## Result/);
assert.deepEqual(extractExecutorResultIdentity(replacedClaim, taskId), {
  legacy: true,
  task_id: taskId,
  identity: null,
});

const mismatch = { ...codex, executor_id: "cursor", executor_product: "cursor" };
const mismatchResult = validateExecutorIdentityMatch(codex, mismatch);
assert.equal(mismatchResult.ok, false);
assert.equal(mismatchResult.code, "executor_identity_mismatch");
assert.deepEqual(mismatchResult.mismatches, ["executor_id", "executor_product"]);

const indentedIdentitySections = `   ## Executor Claim\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\`\n\n  ## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n`;
assert.deepEqual(validatePersistedClaimResult(indentedIdentitySections, taskId), {
  ok: false,
  code: "executor_identity_mismatch",
  legacy: false,
  mismatches: ["executor_id", "executor_product"],
});

const legacy = `---\nstatus: done\n---\n\ntask_id       legacy-task\n`;
assert.equal(taskIdFromText(legacy), "legacy-task");
assert.deepEqual(extractExecutorClaim(legacy), {
  legacy: true,
  task_id: null,
  identity: null,
});
assert.deepEqual(extractExecutorResultIdentity(legacy, "legacy-task"), {
  legacy: true,
  task_id: "legacy-task",
  identity: null,
});
assert.deepEqual(validatePersistedClaimResult(legacy, "legacy-task"), {
  ok: true,
  code: "legacy",
  legacy: true,
  mismatches: [],
});
assert.deepEqual(validateExecutorIdentityMatch(null, null), {
  ok: true,
  code: "legacy",
  legacy: true,
  mismatches: [],
});

for (const specialTaskId of ["a+b", "a[b"]) {
  const specialClaim = upsertExecutorClaim(queued, specialTaskId, codex);
  const specialPersisted = `${specialClaim}\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${specialTaskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\`\n`;
  assert.deepEqual(validatePersistedClaimResult(specialPersisted, specialTaskId), {
    ok: true,
    code: "executor_identity_match",
    legacy: false,
    mismatches: [],
  });
}

const truncatedClaim = `## Executor Claim\n\n- status：\`running\`\n\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\`\n`;
assert.equal(extractExecutorClaim(truncatedClaim).identity, null);
assert.equal(validatePersistedClaimResult(truncatedClaim, taskId).ok, false);

const staleThenDaemon = `${running}\n## Result（human 回寫）\n\n- task_id：\`${taskId}\`\n- status：\`done\`\n\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\`\n`;
assert.deepEqual(extractExecutorResultIdentity(staleThenDaemon, taskId).identity, codex);

const latestResult = `${running}\n## Result（first）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n\n## Result（latest）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\`\n`;
assert.deepEqual(extractExecutorResultIdentity(latestResult, taskId).identity, codex);

const duplicateDaemonResults = `${running}\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n\n## Notes\n\nstale separator\n\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n`;
const reconciledDaemonResult = upsertDaemonResult(
  duplicateDaemonResults,
  `- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\``
);
assert.equal((reconciledDaemonResult.match(/^## Result（inbox-daemon 回寫）$/gm) || []).length, 1);
assert.deepEqual(extractExecutorResultIdentity(reconciledDaemonResult, taskId).identity, codex);

const fencedDaemonExample = `${running}\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n\n## Notes\n\n\`\`\`md~example\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n\nnotes-after-backtick-example\n\n~~~md\`example\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n~~~\n\nnotes-after-tilde-example\n`;
const preservedFencedExample = upsertDaemonResult(
  fencedDaemonExample,
  `- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\``
);
assert.equal((preservedFencedExample.match(/^## Result（inbox-daemon 回寫）$/gm) || []).length, 3);
assert.match(preservedFencedExample, /notes-after-backtick-example/);
assert.match(preservedFencedExample, /notes-after-tilde-example/);
assert.deepEqual(extractExecutorResultIdentity(preservedFencedExample, taskId).identity, codex);

const listNestedDaemonExample = `${running}\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n\n## Notes\n\n- Example output:\n\n  ## Result（inbox-daemon 回寫）\n\n  example-body-must-remain\n\n## Links\n`;
const preservedListExample = upsertDaemonResult(
  listNestedDaemonExample,
  `- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\``
);
assert.match(preservedListExample, /  ## Result（inbox-daemon 回寫）/);
assert.match(preservedListExample, /example-body-must-remain/);
assert.match(preservedListExample, /## Links/);
assert.deepEqual(extractExecutorResultIdentity(preservedListExample, taskId).identity, codex);

const htmlBlockDaemonExample = `${running}\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n\n## Notes\n\n<!--\n## Result（inbox-daemon 回寫）\n- task_id：\`${taskId}\`\ncomment-example-must-remain\n-->\n\n<div>\n## Result（inbox-daemon 回寫）\n- task_id：\`${taskId}\`\nraw-html-example-must-remain\n</div>\n\n<pre>\n## Executor Claim\n- task_id：\`fake-claim\`\n</pre>\n\n## Links\n`;
const preservedHtmlExample = upsertDaemonResult(
  htmlBlockDaemonExample,
  `- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\``
);
assert.match(preservedHtmlExample, /comment-example-must-remain/);
assert.match(preservedHtmlExample, /raw-html-example-must-remain/);
assert.match(preservedHtmlExample, /- task_id：`fake-claim`/);
assert.match(preservedHtmlExample, /## Links/);
assert.equal(
  (preservedHtmlExample.match(/^## Result（inbox-daemon 回寫）$/gm) || []).length,
  3
);
assert.deepEqual(extractExecutorResultIdentity(preservedHtmlExample, taskId).identity, codex);
const claimWithHtmlExamples = upsertExecutorClaim(htmlBlockDaemonExample, taskId, codex);
assert.deepEqual(extractExecutorClaim(claimWithHtmlExamples).identity, codex);
assert.match(claimWithHtmlExamples, /- task_id：`fake-claim`/);

const declaredDaemon = executorIdentityFromEnvironment(
  { CODEX_CLI_AVAILABLE: "1", CURSOR_CLI_AVAILABLE: "1" },
  new Date(claimedAt)
);
assert.equal(declaredDaemon.executor_id, "inbox-daemon");
assert.equal(declaredDaemon.executor_product, "inbox-executor");
assert.notEqual(declaredDaemon.executor_id, "codex");
assert.notEqual(declaredDaemon.executor_id, "cursor");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "executor-identity-e2e-"));
try {
  const inboxDir = path.join(tempRoot, "智能體");
  fs.mkdirSync(inboxDir, { recursive: true });
  fs.writeFileSync(path.join(tempRoot, "sample.md"), "# sample\n", "utf8");
  fs.writeFileSync(
    path.join(inboxDir, "chatgpt-inbox.md"),
    `---\nstatus: queued\n---\n\n## 現在這一份契約\n\n\`\`\`text\ntask_id       ${taskId}\n\`\`\`\n\n## Mechanical Actions\n\n\`\`\`json\n{"actions":[{"tool":"workspace.read","args":{"path":"sample.md"}}]}\n\`\`\`\n\n## Result\n`,
    "utf8"
  );
  const executed = spawnSync(process.execPath, [path.join(__dirname, "daemon.js"), "--once"], {
    encoding: "utf8",
    env: {
      ...process.env,
      VAULT_WORKSPACE_ROOT: tempRoot,
      INBOX_EXECUTOR_IDENTITY: JSON.stringify(codex),
    },
  });
  assert.equal(executed.status, 0, executed.stderr);
  const completed = fs.readFileSync(path.join(inboxDir, "chatgpt-inbox.md"), "utf8");
  assert.match(completed, /^status: done$/m);
  assert.deepEqual(extractExecutorClaim(completed).identity, codex);
  assert.match(completed, /- 結果：done/);
  assert.match(completed, /- identity_validation：`executor_identity_match`/);
  assert.deepEqual(validatePersistedClaimResult(completed, taskId), {
    ok: true,
    code: "executor_identity_match",
    legacy: false,
    mismatches: [],
  });
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

for (const invalidIdentity of ["{", JSON.stringify({ executor_id: "codex" })]) {
  const invalidRoot = fs.mkdtempSync(path.join(os.tmpdir(), "executor-identity-invalid-e2e-"));
  try {
    const inboxDir = path.join(invalidRoot, "智能體");
    fs.mkdirSync(inboxDir, { recursive: true });
    fs.writeFileSync(path.join(invalidRoot, "sample.md"), "# sample\n", "utf8");
    const retryableContract = `---\nstatus: queued\n---\n\n## 現在這一份契約\n\n\`\`\`text\ntask_id       ${taskId}\n\`\`\`\n\n## Mechanical Actions\n\n\`\`\`json\n{"actions":[{"tool":"workspace.read","args":{"path":"sample.md"}}]}\n\`\`\`\n\n## Result\n`;
    fs.writeFileSync(
      path.join(inboxDir, "chatgpt-inbox.md"),
      retryableContract,
      "utf8"
    );
    const executed = spawnSync(process.execPath, [path.join(__dirname, "daemon.js"), "--once"], {
      encoding: "utf8",
      env: {
        ...process.env,
        VAULT_WORKSPACE_ROOT: invalidRoot,
        INBOX_EXECUTOR_IDENTITY: invalidIdentity,
      },
    });
    assert.equal(executed.status, 0, executed.stderr);
    const blocked = fs.readFileSync(path.join(inboxDir, "chatgpt-inbox.md"), "utf8");
    assert.match(blocked, /^status: blocked$/m);
    assert.match(blocked, /- 結果：blocked/);
    assert.match(blocked, /- code：`executor_identity_invalid`/);
    assert.deepEqual(validatePersistedClaimResult(blocked, taskId), {
      ok: false,
      code: "executor_identity_invalid",
      legacy: false,
      mismatches: ["result_identity_invalid"],
    });
    const invalidLedger = JSON.parse(
      fs.readFileSync(path.join(invalidRoot, "runtime", ".inbox-attempts.json"), "utf8")
    );
    assert.equal(invalidLedger.tasks[taskId].identity_configuration_failure, true);

    fs.writeFileSync(path.join(inboxDir, "chatgpt-inbox.md"), retryableContract, "utf8");
    const retried = spawnSync(process.execPath, [path.join(__dirname, "daemon.js"), "--once"], {
      encoding: "utf8",
      env: {
        ...process.env,
        VAULT_WORKSPACE_ROOT: invalidRoot,
        INBOX_EXECUTOR_IDENTITY: JSON.stringify(codex),
      },
    });
    assert.equal(retried.status, 0, retried.stderr);
    const completed = fs.readFileSync(path.join(inboxDir, "chatgpt-inbox.md"), "utf8");
    assert.match(completed, /^status: done$/m);
    assert.match(completed, /- identity_validation：`executor_identity_match`/);

    fs.writeFileSync(path.join(inboxDir, "chatgpt-inbox.md"), retryableContract, "utf8");
    const suppressedAfterRecovery = spawnSync(
      process.execPath,
      [path.join(__dirname, "daemon.js"), "--once"],
      {
        encoding: "utf8",
        env: {
          ...process.env,
          VAULT_WORKSPACE_ROOT: invalidRoot,
          INBOX_EXECUTOR_IDENTITY: JSON.stringify(codex),
        },
      }
    );
    assert.equal(suppressedAfterRecovery.status, 0, suppressedAfterRecovery.stderr);
    const restoredDone = fs.readFileSync(path.join(inboxDir, "chatgpt-inbox.md"), "utf8");
    assert.match(restoredDone, /^status: done$/m);
    assert.doesNotMatch(restoredDone, /## Executor Claim/);
  } finally {
    fs.rmSync(invalidRoot, { recursive: true, force: true });
  }
}

const suppressedRoot = fs.mkdtempSync(path.join(os.tmpdir(), "executor-identity-suppressed-e2e-"));
try {
  const inboxDir = path.join(suppressedRoot, "智能體");
  const runtimeDir = path.join(suppressedRoot, "runtime");
  fs.mkdirSync(inboxDir, { recursive: true });
  fs.mkdirSync(runtimeDir, { recursive: true });
  const suppressedContract = `---\nstatus: queued\n---\n\ntask_id       ${taskId}\n\n## Mechanical Actions\n\n\`\`\`json\n{"actions":[{"tool":"workspace.read","args":{"path":"missing.md"}}]}\n\`\`\`\n`;
  const suppressedResult = `- task_id：\`${taskId}\`\n- 結果：blocked\n- code：\`executor_identity_invalid\`\n- message：post-action validation failed`;
  fs.writeFileSync(path.join(inboxDir, "chatgpt-inbox.md"), suppressedContract, "utf8");
  fs.writeFileSync(
    path.join(runtimeDir, ".inbox-attempts.json"),
    JSON.stringify({
      tasks: {
        [taskId]: {
          hash: contractHash(suppressedContract),
          code: "executor_identity_invalid",
          failure_class: "unknown_side_effect",
          auto_retry: false,
          result_markdown: suppressedResult,
        },
      },
    }),
    "utf8"
  );
  const suppressed = spawnSync(process.execPath, [path.join(__dirname, "daemon.js"), "--once"], {
    encoding: "utf8",
    env: {
      ...process.env,
      VAULT_WORKSPACE_ROOT: suppressedRoot,
      INBOX_EXECUTOR_IDENTITY: JSON.stringify(codex),
    },
  });
  assert.equal(suppressed.status, 0, suppressed.stderr);
  const restored = fs.readFileSync(path.join(inboxDir, "chatgpt-inbox.md"), "utf8");
  assert.match(restored, /^status: blocked$/m);
  assert.match(restored, /post-action validation failed/);
  assert.doesNotMatch(restored, /## Executor Claim/);
} finally {
  fs.rmSync(suppressedRoot, { recursive: true, force: true });
}

if (process.env.INBOX_IDENTITY_VERIFY_PATH) {
  const persisted = fs.readFileSync(process.env.INBOX_IDENTITY_VERIFY_PATH, "utf8");
  assert.deepEqual(validatePersistedClaimResult(persisted, taskId), {
    ok: true,
    code: "executor_identity_match",
    legacy: false,
    mismatches: [],
  });
}

console.log("EXECUTOR_IDENTITY_E2E_PASS");
