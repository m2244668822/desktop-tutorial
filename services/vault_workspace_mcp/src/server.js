#!/usr/bin/env node
/**
 * Minimal MCP stdio server for vault-scoped workspace tools.
 * Transport: MCP stdio using newline-delimited JSON-RPC by default.
 * Legacy Content-Length output remains opt-in via MCP_FRAMING=content-length.
 */

import readline from "node:readline";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { VaultWorkspace, TOOL_DEFS, dispatch } from "./workspace.js";

const HOST_TOOL_NAME_BY_INTERNAL = Object.freeze({
  "workspace.list": "workspace_list",
  "workspace.search": "workspace_search",
  "workspace.read": "workspace_read",
  "workspace.propose_patch": "workspace_propose_patch",
  "runtime.capabilities": "runtime_capabilities",
  "runtime.run_test": "runtime_run_test",
  "trevor.web_search": "trevor_web_search",
  "workspace.create": "workspace_create",
  "workspace.patch": "workspace_patch",
  "workspace.move": "workspace_move",
  "workspace.trash": "workspace_trash",
});

const INTERNAL_TOOL_NAME_BY_HOST = Object.freeze(
  Object.fromEntries(
    Object.entries(HOST_TOOL_NAME_BY_INTERNAL).map(([internal, host]) => [host, internal]),
  ),
);

function hostToolDefs() {
  return TOOL_DEFS.map((tool) => {
    const hostTool = {
      ...tool,
      name: HOST_TOOL_NAME_BY_INTERNAL[tool.name] || tool.name.replace(/[^a-z0-9_-]/gi, "_"),
    };
    if (rtsEvidence && tool.name === "runtime.run_test") {
      hostTool.description = "Run only the fixed Node test suite in the assigned RTS fixture.";
      hostTool.inputSchema = {
        type: "object",
        properties: {
          runner: { type: "string", enum: ["node_test"] },
          target: { type: "string", enum: ["tests"] },
        },
        required: ["runner", "target"],
        additionalProperties: false,
      };
    }
    return hostTool;
  });
}

function rtsDenialReason(name, args) {
  if (!rtsTools.has(name)) return "tool_not_allowed";
  if (name === "workspace.read" && args.path !== "tests/fixture.test.js") return "workspace_read_path";
  if (name === "workspace.list" && args.dir && args.dir !== ".") return "workspace_list_dir";
  if (name === "runtime.run_test") {
    if (args.runner !== "node_test") return "runtime_test_runner";
    if (args.target !== "tests") return "runtime_test_target";
    if (Object.hasOwn(args, "projectDir")) return "runtime_test_project_dir";
    if (Object.keys(args).some((key) => !["runner", "target"].includes(key))) return "runtime_test_extra_argument";
  }
  return null;
}

function internalToolName(name) {
  return INTERNAL_TOOL_NAME_BY_HOST[name] || name;
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function defaultVaultRoot() {
  // Resolve the runtime repo first, then infer the vault root for the
  // supported layouts:
  //   <vault>/runtime/desktop-tutorial/...
  //   <vault>/apps/angel-runtime/...
  // Direct checkout under <vault>/desktop-tutorial is also supported.
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const parent = path.dirname(repoRoot);
  const containerName = path.basename(parent).toLowerCase();
  if (containerName === "runtime" || containerName === "apps") {
    return path.dirname(parent);
  }
  return parent;
}

const workspaceRoot = process.env.VAULT_WORKSPACE_ROOT || defaultVaultRoot();
const auditDir =
  process.env.MCP_AUDIT_DIR ||
  path.join(workspaceRoot, "runtime", ".mcp-audit");
const trashDir =
  process.env.MCP_TRASH_DIR ||
  path.join(workspaceRoot, "runtime", ".mcp-trash");
const autoApprove = process.env.MCP_AUTO_APPROVE === "1";
const rtsEvidence = process.env.RTS01_MCP_EVIDENCE;
const rtsTools = new Set(["workspace.list", "workspace.read", "runtime.capabilities", "runtime.run_test"]);

function recordRts(method, outcome = "ok") {
  if (rtsEvidence) {
    fs.appendFileSync(rtsEvidence, JSON.stringify({ method, outcome, root: path.resolve(workspaceRoot) }) + "\n");
  }
}

const ws = new VaultWorkspace({
  workspaceRoot,
  auditDir,
  trashDir,
  autoApprove,
});

function send(msg) {
  const body = JSON.stringify(msg);
  // MCP stdio clients expect one JSON-RPC message per line.
  // Keep legacy Content-Length framing only when explicitly requested.
  const framing = String(process.env.MCP_FRAMING || "newline").toLowerCase();
  const useCL =
    framing === "content-length" ||
    framing === "content_length" ||
    framing === "cl";
  if (useCL) {
    process.stdout.write(`Content-Length: ${Buffer.byteLength(body, "utf8")}\r\n\r\n${body}`);
  } else {
    process.stdout.write(body + "\n");
  }
}

async function handle(msg) {
  const { id, method, params } = msg;
  if (method === "initialize") {
    recordRts(method);
    return {
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "vault-workspace-mcp", version: "0.1.0" },
      },
    };
  }
  if (method === "notifications/initialized" || method === "initialized") {
    return null;
  }
  if (method === "tools/list") {
    recordRts(method);
    return {
      jsonrpc: "2.0",
      id,
      result: { tools: hostToolDefs().filter(tool => !rtsEvidence || rtsTools.has(internalToolName(tool.name))) },
    };
  }
  if (method === "tools/call") {
    const requestedName = params?.name;
    const name = internalToolName(requestedName);
    const evidenceName = rtsTools.has(name) ? name : "other_tool";
    const args = params?.arguments || {};
    try {
      recordRts(evidenceName, "attempt");
      const denialReason = rtsEvidence ? rtsDenialReason(name, args) : null;
      if (denialReason) {
        throw Object.assign(new Error("Tool or arguments outside the RTS fixture profile"), {
          code: "rts01_tool_denied",
          reason: denialReason,
        });
      }
      const result = await dispatch(ws, name, rtsEvidence && name === "runtime.run_test"
        ? { runner: "node_test", target: "tests", timeoutSec: 60 }
        : args);
      recordRts(evidenceName, name !== "runtime.run_test" || (result.ok && result.exit_code === 0) ? "ok" : "test_failed");
      return {
        jsonrpc: "2.0",
        id,
        result: {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        },
      };
    } catch (err) {
      recordRts(evidenceName, err.code === "rts01_tool_denied" ? `denied:${err.reason || "policy"}` : "dispatch_error");
      return {
        jsonrpc: "2.0",
        id,
        result: {
          isError: true,
          content: [
            {
              type: "text",
              text: JSON.stringify({
                error: err.code || "error",
                message: err.message,
                level: err.level,
              }),
            },
          ],
        },
      };
    }
  }
  if (method === "ping") {
    return { jsonrpc: "2.0", id, result: {} };
  }
  return {
    jsonrpc: "2.0",
    id,
    error: { code: -32601, message: `Method not found: ${method}` },
  };
}

let buffer = Buffer.alloc(0);

function tryParseContentLength() {
  while (true) {
    const headerEnd = buffer.indexOf("\r\n\r\n");
    if (headerEnd === -1) return false;
    const header = buffer.slice(0, headerEnd).toString("utf8");
    const m = /Content-Length:\s*(\d+)/i.exec(header);
    if (!m) {
      // fallback: treat as newline JSON
      return false;
    }
    const len = Number(m[1]);
    const bodyStart = headerEnd + 4;
    if (buffer.length < bodyStart + len) return true; // wait more
    const body = buffer.slice(bodyStart, bodyStart + len).toString("utf8");
    buffer = buffer.slice(bodyStart + len);
    queueMicrotask(() => onMessage(body));
  }
}

async function onMessage(raw) {
  let msg;
  try {
    msg = JSON.parse(raw);
  } catch {
    return;
  }
  if (Array.isArray(msg)) {
    for (const m of msg) {
      const res = await handle(m);
      if (res) send(res);
    }
    return;
  }
  const res = await handle(msg);
  if (res) send(res);
}

process.stdin.on("data", (chunk) => {
  buffer = Buffer.concat([buffer, chunk]);
  if (buffer.includes("Content-Length:")) {
    tryParseContentLength();
    return;
  }
  // newline-delimited JSON
  const text = buffer.toString("utf8");
  const parts = text.split("\n");
  buffer = Buffer.from(parts.pop() || "", "utf8");
  for (const line of parts) {
    if (line.trim()) queueMicrotask(() => onMessage(line));
  }
});


process.stderr.write(
  `[vault-workspace-mcp] root=${workspaceRoot} autoApprove=${autoApprove}\n`
);
