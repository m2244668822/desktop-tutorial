import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { probeMcpProtocol } from "../src/mcp_protocol_probe.js";
import { resolveMcpServerPath } from "../src/mcp_server_path.js";

test("MCP probe records the exact protocol stage for an invalid initialize response", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "rts01-mcp-probe-invalid-"));
  const server = path.join(root, "invalid-initialize.mjs");
  await fs.writeFile(
    server,
    [
      "process.stdin.on('data', () => {",
      "  process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:1,result:{serverInfo:{name:'wrong-server'}}}) + '\\n');",
      "});",
    ].join("\n"),
    "utf8",
  );

  const result = await probeMcpProtocol({
    serverPath: server,
    workspaceRoot: root,
    auditDir: path.join(root, "audit"),
    trashDir: path.join(root, "trash"),
  });

  assert.equal(result.ok, false);
  assert.equal(result.blocker, "mcp_initialize_invalid");
  assert.equal(result.evidence.diagnostic.stage, "initialize");
});

test("MCP probe normalizes a missing server path without leaking process details", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "rts01-mcp-probe-start-"));
  const result = await probeMcpProtocol({
    serverPath: path.join(root, "missing-server.mjs"),
    workspaceRoot: root,
    auditDir: path.join(root, "audit"),
    trashDir: path.join(root, "trash"),
  });

  assert.equal(result.ok, false);
  assert.equal(result.blocker, "mcp_server_spawn_failed");
  assert.equal(result.evidence.diagnostic.stage, "spawn");
  assert.equal(result.evidence.diagnostic.stderr_length, 0);
});


test("MCP server path resolution falls back to the initialized source runtime", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "rts01-mcp-path-"));
  const sourceRoot = path.join(root, "source");
  const worktreeRoot = path.join(root, "worktree");
  const runtimeRoot = path.join(root, "runtime-mirror");
  const server = path.join(sourceRoot, "services", "vault_workspace_mcp", "src", "server.js");
  await fs.mkdir(path.dirname(server), { recursive: true });
  await fs.writeFile(server, "// fixture", "utf8");

  assert.equal(
    resolveMcpServerPath({ sourceRepoRoot: sourceRoot, worktreeRoot, runtimeRoot }),
    server,
  );
});

test("MCP server path resolution prefers the explicit runtime mirror", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "rts01-mcp-path-prefer-"));
  const runtimeRoot = path.join(root, "runtime-mirror");
  const worktreeRoot = path.join(root, "worktree");
  const sourceRoot = path.join(root, "source");
  const server = path.join(runtimeRoot, "services", "vault_workspace_mcp", "src", "server.js");
  await fs.mkdir(path.dirname(server), { recursive: true });
  await fs.writeFile(server, "// fixture", "utf8");

  assert.equal(
    resolveMcpServerPath({ sourceRepoRoot: sourceRoot, worktreeRoot, runtimeRoot }),
    server,
  );
});
