import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

test("strict acceptance blocks an unverifiable run before writing a Claim", () => {
  const fixture = mkdtempSync(path.join(os.tmpdir(), "rts01-auth-test-"));
  try {
    const task = path.join(fixture, "task.md");
    writeFileSync(task, [
      "---", "status: queued", "---", "# Strict auth fixture",
      "task_id rts01-auth-test", "status queued", "route agentic",
      "executor codex", "auth_mode chatgpt", "project automation-fixture",
      "Output implementation", "",
    ].join("\n"));
    const executor = fileURLToPath(new URL("./agentic_executor.js", import.meta.url));
    const result = spawnSync(process.execPath, [executor], {
      env: { ...process.env, VAULT_WORKSPACE_ROOT: fixture, INBOX_PATH: task, GITHUB_RUN_ID: "" },
      encoding: "utf8",
      timeout: 45000,
    });
    assert.equal(result.status, 4, result.stderr);
    assert.match(result.stderr, /RTS01_STRICT_AUTH_GATE_BLOCKED before_claim=true/);
    const saved = readFileSync(task, "utf8");
    assert.match(saved, /^status: blocked$/m);
    assert.match(saved, /strict_agentic_auth_gate_failed/);
    assert.doesNotMatch(saved, /^## Executor Claim/m);
  } finally {
    rmSync(fixture, { recursive: true, force: true, maxRetries: 12, retryDelay: 150 });
  }
});

test("strict MCP records the fixture path and only permits the bounded test", () => {
  const fixture = mkdtempSync(path.join(os.tmpdir(), "rts01-mcp-test-"));
  try {
    const root = path.join(fixture, "fixture");
    const evidence = path.join(fixture, "evidence.jsonl");
    mkdirSync(path.join(root, "tests"), { recursive: true });
    writeFileSync(path.join(root, "tests", "fixture.test.js"), "if (process.env.CI !== '1') process.exit(1);\n");
    const calls = [
      ["initialize", {}], ["tools/list", {}],
      ["tools/call", { name: "workspace_list", arguments: {} }],
      ["tools/call", { name: "workspace_read", arguments: { path: "tests/fixture.test.js" } }],
      ["tools/call", { name: "runtime_run_test", arguments: { runner: "node_test", target: "tests" } }],
      ["tools/call", { name: "runtime_run_test", arguments: { runner: "pytest", target: "tests" } }],
    ];
    const input = calls.map(([method, params], id) => JSON.stringify({ jsonrpc: "2.0", id, method, params })).join("\n") + "\n";
    const server = fileURLToPath(new URL("../../vault_workspace_mcp/src/server.js", import.meta.url));
    const result = spawnSync(process.execPath, [server], {
      env: { ...process.env, VAULT_WORKSPACE_ROOT: root, RTS01_MCP_EVIDENCE: evidence,
        MCP_AUDIT_DIR: path.join(fixture, "audit"), MCP_TRASH_DIR: path.join(fixture, "trash"), MCP_FRAMING: "newline" },
      input, encoding: "utf8", timeout: 45000,
    });
    assert.equal(result.status, 0, result.stderr);
    const responses = result.stdout.trim().split(/\r?\n/).map(line => JSON.parse(line));
    assert.equal(responses.find(row => row.id === 5)?.result?.isError, true);
    const rows = readFileSync(evidence, "utf8").trim().split(/\r?\n/).map(line => JSON.parse(line));
    assert.deepEqual(rows.map(row => row.method).sort(),
      ["initialize", "runtime.run_test", "tools/list", "workspace.list", "workspace.read"]);
    assert.ok(rows.every(row => row.root === root));
  } finally {
    rmSync(fixture, { recursive: true, force: true, maxRetries: 12, retryDelay: 150 });
  }
});
