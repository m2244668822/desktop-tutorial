#!/usr/bin/env node
/**
 * Minimal MCP stdio server for vault-scoped workspace tools.
 * Transport: MCP stdio using newline-delimited JSON-RPC by default.
 * Legacy Content-Length output remains opt-in via MCP_FRAMING=content-length.
 */

import readline from "node:readline";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { VaultWorkspace, TOOL_DEFS, dispatch } from "./workspace.js";

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
    return {
      jsonrpc: "2.0",
      id,
      result: { tools: TOOL_DEFS },
    };
  }
  if (method === "tools/call") {
    const name = params?.name;
    const args = params?.arguments || {};
    try {
      const result = await dispatch(ws, name, args);
      return {
        jsonrpc: "2.0",
        id,
        result: {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        },
      };
    } catch (err) {
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

process.stdin.on("end", () => process.exit(0));

process.stderr.write(
  `[vault-workspace-mcp] root=${workspaceRoot} autoApprove=${autoApprove}\n`
);
