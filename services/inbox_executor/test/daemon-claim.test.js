import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const daemonPath = path.resolve(import.meta.dirname, "../src/daemon.js");

test("policy denial writes operation_id in claim and blocked Result", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "inbox-operation-id-"));
  const taskPath = path.join(root, "task.md");
  fs.mkdirSync(path.join(root, "runtime"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "runtime", "test-profiles.json"),
    JSON.stringify({
      policy: { unknown_project: "blocked" },
      projects: {
        "automation-fixture": {
          root: "runtime/.mcp-automation-fixture",
          automation_mode: "manual_only",
          policy_scope: "disposable",
        },
      },
    }),
    "utf8"
  );
  fs.writeFileSync(
    taskPath,
    `---\nstatus: queued\n---\n\ntask_id       operation-id-policy-denial\nproject       automation-fixture\n\n## Mechanical Actions\n\n\`\`\`json\n{"executor":"inbox-daemon","actions":[{"tool":"runtime.run_test","args":{"projectDir":".","runner":"node_test","target":"tests","timeoutSec":60}}]}\n\`\`\`\n`,
    "utf8"
  );

  const result = spawnSync(process.execPath, [daemonPath, "--once"], {
    cwd: path.resolve(import.meta.dirname, ".."),
    encoding: "utf8",
    env: {
      ...process.env,
      VAULT_WORKSPACE_ROOT: root,
      INBOX_PATH: taskPath,
      INBOX_EXECUTOR_ID: "github-actions-self-hosted",
      INBOX_EXECUTOR_TYPE: "external",
      INBOX_EXECUTOR_PROVIDER: "github",
      INBOX_EXECUTOR_PRODUCT: "actions-runner",
      INBOX_EXECUTOR_MODE: "self-hosted-windows",
      INBOX_EXECUTOR_VERSION: "actions-runner",
      INBOX_EXECUTOR_CAPABILITIES: "bounded-tests",
      INBOX_AUTO_APPROVE: "0",
    },
  });

  assert.equal(result.status, 0, result.stderr);
  const persisted = fs.readFileSync(taskPath, "utf8");
  assert.match(persisted, /^status: blocked$/m);
  assert.match(persisted, /- operation_id：`op-[a-f0-9]{24}`/);
  assert.match(persisted, /- code：`manual_only_project`/);
  assert.match(persisted, /- identity_validation：`executor_identity_match`/);
});

test("registered disposable fixture permits bounded runtime.run_test", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "inbox-runtime-test-policy-"));
  const taskPath = path.join(root, "task.md");
  const fixtureTests = path.join(root, "runtime", ".mcp-automation-fixture", "tests");
  fs.mkdirSync(fixtureTests, { recursive: true });
  fs.writeFileSync(
    path.join(fixtureTests, "pass.test.mjs"),
    "import test from 'node:test'; test('fixture pass', () => {});\n",
    "utf8",
  );
  fs.mkdirSync(path.join(root, "runtime"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "runtime", "test-profiles.json"),
    JSON.stringify({
      policy: { unknown_project: "blocked" },
      projects: {
        "automation-fixture": {
          root: "runtime/.mcp-automation-fixture",
          automation_mode: "bounded_write",
          policy_scope: "disposable",
          allowed_write_tools: [],
          allowed_test_tools: ["runtime.run_test"],
        },
      },
    }),
    "utf8",
  );
  fs.writeFileSync(
    taskPath,
    `---\nstatus: queued\n---\n\ntask_id       runtime-test-policy\nproject       automation-fixture\n\n## Mechanical Actions\n\n\`\`\`json
{"executor":"inbox-daemon","actions":[{"tool":"runtime.run_test","args":{"projectDir":"runtime/.mcp-automation-fixture","runner":"node_test","target":"tests","timeoutSec":60}}]}\n\`\`\`\n`,
    "utf8",
  );
  for (const args of [
    ["init"],
    ["config", "user.email", "test@example.invalid"],
    ["config", "user.name", "Inbox Test"],
    ["add", "."],
    ["-c", "user.email=test@example.invalid", "-c", "user.name=Inbox Test", "commit", "-m", "fixture"],
  ]) {
    const git = spawnSync("git", ["-C", root, ...args], { encoding: "utf8" });
    assert.equal(git.status, 0, git.stderr);
  }

  const result = spawnSync(process.execPath, [daemonPath, "--once"], {
    cwd: path.resolve(import.meta.dirname, ".."),
    encoding: "utf8",
    env: {
      ...process.env,
      VAULT_WORKSPACE_ROOT: root,
      INBOX_PATH: taskPath,
      INBOX_EXECUTOR_ID: "github-actions-self-hosted",
      INBOX_EXECUTOR_TYPE: "external",
      INBOX_EXECUTOR_PROVIDER: "github",
      INBOX_EXECUTOR_PRODUCT: "actions-runner",
      INBOX_EXECUTOR_MODE: "self-hosted-windows",
      INBOX_EXECUTOR_VERSION: "actions-runner",
      INBOX_EXECUTOR_CAPABILITIES: "bounded-tests",
      INBOX_AUTO_APPROVE: "0",
    },
  });

  assert.equal(result.status, 0, result.stderr);
  const persisted = fs.readFileSync(taskPath, "utf8");
  assert.match(persisted, /^status: done$/m);
  assert.match(persisted, /- operation_id：`op-[a-f0-9]{24}`/);
  assert.match(persisted, /- `runtime\.run_test` ok/);
});
