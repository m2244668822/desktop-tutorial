#!/usr/bin/env node
/**
 * L1/L2 E2E: read → propose patch → approved patch → verify → safe scratch restore
 * Isolated git repo under runtime/.mcp-e2e-scratch (does not commit the vault).
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { VaultWorkspace, TOOL_DEFS, dispatch } from "./workspace.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(__dirname, "..", "..", "..", "..");
const scratchRoot = path.join(vaultRoot, "runtime", ".mcp-e2e-scratch");
const auditDir = path.join(scratchRoot, ".mcp-audit");
const trashDir = path.join(scratchRoot, ".mcp-trash");

fs.rmSync(scratchRoot, { recursive: true, force: true });
fs.mkdirSync(scratchRoot, { recursive: true });

function git(args) {
  const r = spawnSync("git", args, { cwd: scratchRoot, encoding: "utf8" });
  if (r.status !== 0) throw new Error(`git ${args.join(" ")} failed: ${r.stderr}`);
  return r.stdout.trim();
}

git(["init"]);
git(["config", "user.email", "mcp-e2e@local"]);
git(["config", "user.name", "mcp-e2e"]);

const relFile = "e2e-target.md";
fs.writeFileSync(path.join(scratchRoot, relFile), "# e2e before\n", "utf8");
fs.mkdirSync(path.join(scratchRoot, "services", "smoke", "src"), { recursive: true });
fs.writeFileSync(
  path.join(scratchRoot, "services", "smoke", "src", "e2e.js"),
  "console.log('SMOKE_OK');\n",
  "utf8",
);

fs.mkdirSync(path.join(scratchRoot, "projects", "npm-smoke", "tests"), { recursive: true });
fs.writeFileSync(
  path.join(scratchRoot, "projects", "npm-smoke", "package.json"),
  JSON.stringify(
    {
      name: "npm-smoke",
      private: true,
      type: "module",
      scripts: { test: "node --test" },
    },
    null,
    2,
  ) + "\n",
  "utf8",
);
fs.writeFileSync(
  path.join(scratchRoot, "projects", "npm-smoke", "tests", "basic.test.js"),
  "import test from 'node:test';\nimport assert from 'node:assert/strict';\ntest('ok', () => assert.equal(1, 1));\n",
  "utf8",
);

fs.mkdirSync(path.join(scratchRoot, "projects", "static-smoke"), { recursive: true });
fs.writeFileSync(
  path.join(scratchRoot, "projects", "static-smoke", "index.html"),
  "<!doctype html><script src=\"app.js\"></script>\n",
  "utf8",
);
fs.writeFileSync(
  path.join(scratchRoot, "projects", "static-smoke", "app.js"),
  "const ready = true;\nconsole.log(ready);\n",
  "utf8",
);

git(["add", "-A"]);
git(["commit", "-m", "e2e-seed"]);

const ws = new VaultWorkspace({
  workspaceRoot: scratchRoot,
  auditDir,
  trashDir,
  autoApprove: true,
});

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const read1 = await ws.read({ path: relFile });
assert(read1.content.includes("e2e before"), "read failed");

const toolNames = new Set(TOOL_DEFS.map((item) => item.name));
for (const expected of [
  "workspace.propose_patch",
  "runtime.capabilities",
  "runtime.run_test",
  "trevor.web_search",
]) {
  assert(toolNames.has(expected), `missing internal MCP tool: ${expected}`);
}
assert(!toolNames.has("git.checkpoint"), "git.checkpoint must not be exposed as an MCP tool");

const runtime = await dispatch(ws, "runtime.capabilities", {});
assert(runtime.executors?.workspace_mcp === true, "runtime capabilities missing workspace_mcp");
assert(
  Object.prototype.hasOwnProperty.call(runtime.executors || {}, "codex_cli"),
  "runtime capabilities missing codex_cli",
);
assert(
  runtime.executor_readiness?.vscode?.interactive_only === true,
  "VS Code must remain interactive_only",
);

const testRun = await dispatch(ws, "runtime.run_test", {
  runner: "node_e2e",
  target: "services/smoke/src/e2e.js",
  timeoutSec: 30,
});
assert(testRun.ok === true, `runtime.run_test failed: ${testRun.stderr}`);
assert(testRun.exit_code === 0, "runtime.run_test exit code mismatch");
assert(testRun.stdout.includes("SMOKE_OK"), "runtime.run_test output mismatch");

const nodeTest = await dispatch(ws, "runtime.run_test", {
  runner: "node_test",
  projectDir: "projects/npm-smoke",
  target: "tests",
  timeoutSec: 60,
});
assert(nodeTest.ok === true, `node_test failed:\nstdout=${nodeTest.stdout}\nstderr=${nodeTest.stderr}`);
assert(nodeTest.exit_code === 0, "node_test exit code mismatch");

// Sanitized test env must forward PATHEXT (Windows cmd.exe/shell command resolution)
// and must still drop non-whitelisted variables. Deterministic: sentinel values are set
// here, not read from the host.
{
  const pathextSentinel = ".COM;.EXE;.BAT;.CMD;.E2E";
  const previousPathext = process.env.PATHEXT;
  const previousProbe = process.env.VAULT_E2E_ENV_PROBE;
  process.env.PATHEXT = pathextSentinel;
  process.env.VAULT_E2E_ENV_PROBE = "must-not-leak";
  fs.writeFileSync(
    path.join(scratchRoot, "projects", "npm-smoke", "tests", "env.test.js"),
    [
      "import test from 'node:test';",
      "import assert from 'node:assert/strict';",
      `test('PATHEXT forwarded', () => assert.equal(process.env.PATHEXT, ${JSON.stringify(pathextSentinel)}));`,
      "test('non-whitelisted env dropped', () => assert.equal(process.env.VAULT_E2E_ENV_PROBE, undefined));",
      "",
    ].join("\n"),
    "utf8",
  );
  try {
    const envTest = await dispatch(ws, "runtime.run_test", {
      runner: "node_test",
      projectDir: "projects/npm-smoke",
      target: "tests/env.test.js",
      timeoutSec: 60,
    });
    assert(envTest.ok === true, `node_test env check failed:\nstdout=${envTest.stdout}\nstderr=${envTest.stderr}`);
    assert(envTest.exit_code === 0, "node_test env check exit code mismatch");
  } finally {
    if (previousPathext === undefined) delete process.env.PATHEXT;
    else process.env.PATHEXT = previousPathext;
    if (previousProbe === undefined) delete process.env.VAULT_E2E_ENV_PROBE;
    else process.env.VAULT_E2E_ENV_PROBE = previousProbe;
  }
}

const staticSmoke = await dispatch(ws, "runtime.run_test", {
  runner: "static_smoke",
  projectDir: "projects/static-smoke",
  target: "index.html",
  timeoutSec: 30,
});
assert(staticSmoke.ok === true, `static_smoke failed: ${staticSmoke.stderr}`);
assert(staticSmoke.stdout.includes("app.js"), "static_smoke must inspect top-level JS");

let deniedNodeOutsideProject = false;
try {
  await dispatch(ws, "runtime.run_test", {
    runner: "node_test",
    projectDir: "../outside",
    target: "tests",
    timeoutSec: 30,
  });
} catch (error) {
  deniedNodeOutsideProject =
    error?.code === "path_outside_workspace" ||
    error?.code === "test_project_missing" ||
    error?.code === "test_project_outside_workspace";
}
assert(deniedNodeOutsideProject, "node_test must deny projects outside workspace");

if (process.platform !== "win32") {
  const outsideRoot = fs.mkdtempSync(path.join(os.tmpdir(), "mcp-test-outside-"));
  try {
    fs.mkdirSync(path.join(outsideRoot, "tests"), { recursive: true });
    fs.writeFileSync(
      path.join(outsideRoot, "tests", "escape.test.js"),
      "import test from 'node:test'; test('escape', () => {});\n",
      "utf8",
    );
    fs.symlinkSync(outsideRoot, path.join(scratchRoot, "projects", "escape-link"), "dir");
    let deniedSymlinkProject = false;
    try {
      await dispatch(ws, "runtime.run_test", {
        runner: "node_test",
        projectDir: "projects/escape-link",
        target: "tests",
        timeoutSec: 30,
      });
    } catch (error) {
      deniedSymlinkProject = error?.code === "test_project_outside_workspace";
    }
    assert(deniedSymlinkProject, "symlinked project outside workspace must be denied");
  } finally {
    fs.rmSync(outsideRoot, { recursive: true, force: true });
  }
}

let deniedTestTarget = false;
try {
  await dispatch(ws, "runtime.run_test", {
    runner: "node_e2e",
    target: "e2e-target.md",
    timeoutSec: 30,
  });
} catch (error) {
  deniedTestTarget = error?.code === "node_e2e_target_denied";
}
assert(deniedTestTarget, "runtime.run_test must deny arbitrary node targets");

const originalFetch = globalThis.fetch;
globalThis.fetch = async () =>
  new Response(
    JSON.stringify({
      ok: true,
      query: "VS Code MCP",
      source: "test",
      redaction_count: 0,
      results: [
        {
          title: "VS Code MCP",
          url: "https://code.visualstudio.com/",
          snippet: "Official documentation",
        },
      ],
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
try {
  const search = await dispatch(ws, "trevor.web_search", {
    query: "VS Code MCP",
    limit: 3,
  });
  assert(search.ok === true, "trevor.web_search failed");
  assert(search.results.length === 1, "trevor.web_search result mismatch");
} finally {
  globalThis.fetch = originalFetch;
}

const proposed = await ws.proposePatch({
  path: relFile,
  content: "# e2e after\n",
});
assert(proposed.diff_hash, "missing diff_hash");
console.log("diff_hash", proposed.diff_hash);

const patched = await ws.patch({
  path: relFile,
  content: "# e2e after\n",
  approval: {
    approved: true,
    action_id: proposed.action_id,
    diff_hash: proposed.diff_hash,
    expires_at: new Date(Date.now() + 600_000).toISOString(),
  },
});
assert(patched.hash === proposed.after_hash, "hash mismatch after patch");

const read2 = await ws.read({ path: relFile });
assert(read2.content.includes("e2e after"), "patch not applied");

fs.writeFileSync(path.join(scratchRoot, relFile), read1.content, "utf8");
const read3 = await ws.read({ path: relFile });
assert(read3.content.includes("e2e before"), "safe scratch restore did not restore content");

const auditPath = path.join(auditDir, "mcp-audit.jsonl");
assert(fs.existsSync(auditPath), "audit log missing");
const last = fs.readFileSync(auditPath, "utf8").trim().split("\n").pop();
console.log("audit_last", last);

async function stdioHandshake() {
  const serverPath = path.join(__dirname, "server.js");
  const env = {
    ...process.env,
    VAULT_WORKSPACE_ROOT: scratchRoot,
    MCP_AUTO_APPROVE: "0",
  };
  delete env.MCP_FRAMING;

  const child = spawn(process.execPath, [serverPath], {
    cwd: path.dirname(serverPath),
    env,
    stdio: ["pipe", "pipe", "pipe"],
  });

  let stdoutBuffer = "";
  let stderrBuffer = "";
  const pending = new Map();

  const rejectAll = (error) => {
    for (const { reject, timer } of pending.values()) {
      clearTimeout(timer);
      reject(error);
    }
    pending.clear();
  };

  child.stderr.on("data", (chunk) => {
    stderrBuffer += chunk.toString("utf8");
  });

  child.stdout.on("data", (chunk) => {
    stdoutBuffer += chunk.toString("utf8");
    const lines = stdoutBuffer.split(/\r?\n/);
    stdoutBuffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        continue;
      }
      if (message.id == null || !pending.has(message.id)) continue;
      const entry = pending.get(message.id);
      pending.delete(message.id);
      clearTimeout(entry.timer);
      entry.resolve(message);
    }
  });

  child.on("error", rejectAll);
  child.on("exit", (code) => {
    if (pending.size) {
      rejectAll(new Error(`stdio MCP exited early code=${code} stderr=${stderrBuffer}`));
    }
  });

  const request = (id, method, params = {}) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(
          new Error(
            `stdio MCP timeout method=${method} stdout=${stdoutBuffer} stderr=${stderrBuffer}`,
          ),
        );
      }, 5000);
      pending.set(id, { resolve, reject, timer });
      child.stdin.write(
        JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n",
      );
    });

  try {
    const initialized = await request(100, "initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "vault-workspace-e2e", version: "1.0.0" },
    });
    assert(
      initialized.result?.serverInfo?.name === "vault-workspace-mcp",
      "stdio initialize failed",
    );

    child.stdin.write(
      JSON.stringify({
        jsonrpc: "2.0",
        method: "notifications/initialized",
        params: {},
      }) + "\n",
    );

    const listed = await request(101, "tools/list", {});
    const listedTools = listed.result?.tools || [];
    const names = new Set(listedTools.map((tool) => tool.name));
    for (const expected of [
      "workspace_read",
      "workspace_propose_patch",
      "runtime_capabilities",
      "runtime_run_test",
    ]) {
      assert(names.has(expected), `stdio tools/list missing ${expected}`);
    }
    for (const tool of listedTools) {
      assert(
        /^[a-z0-9_-]+$/i.test(String(tool.name || "")),
        `stdio tools/list exposed invalid host tool name: ${tool.name}`,
      );
    }

    const capabilities = await request(102, "tools/call", {
      name: "runtime_capabilities",
      arguments: {},
    });
    const capabilityText = capabilities.result?.content?.[0]?.text || "";
    assert(
      capabilityText.includes('"workspace_mcp": true'),
      "stdio tools/call runtime_capabilities failed",
    );

    console.log("STDIO_HOST_TOOL_NAMES_PASS");
    console.log("STDIO_TOOL_CALL_PASS");
    console.log("STDIO_HANDSHAKE_PASS");
  } finally {
    child.stdin.end();
    child.kill();
  }
}

await stdioHandshake();
console.log("E2E_PASS");
