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
import { contractHash, taskIdFromText, upsertDaemonResult } from "./inbox.js";

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
const queued = `---\nstatus: queued\n---\n\ntask_id       ${taskId}\n\n## Result\n`;
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

const fencedDaemonExample = `${running}\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n\n## Notes\n\n\`\`\`md\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n\nnotes-after-backtick-example\n\n~~~md\n## Result（inbox-daemon 回寫）\n\n- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(mismatch, null, 2)}\n\`\`\`\n~~~\n\nnotes-after-tilde-example\n`;
const preservedFencedExample = upsertDaemonResult(
  fencedDaemonExample,
  `- task_id：\`${taskId}\`\n- executor_identity：\n\`\`\`json\n${JSON.stringify(codex, null, 2)}\n\`\`\``
);
assert.equal((preservedFencedExample.match(/^## Result（inbox-daemon 回寫）$/gm) || []).length, 3);
assert.match(preservedFencedExample, /notes-after-backtick-example/);
assert.match(preservedFencedExample, /notes-after-tilde-example/);
assert.deepEqual(extractExecutorResultIdentity(preservedFencedExample, taskId).identity, codex);

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
