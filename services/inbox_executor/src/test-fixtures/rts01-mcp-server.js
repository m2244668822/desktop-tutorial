import fs from "node:fs";
import path from "node:path";

const root = process.env.VAULT_WORKSPACE_ROOT;
let buffer = "";
function send(message) {
  process.stdout.write(JSON.stringify(message) + "\n");
}
function list() {
  return { workspace_root: root, entries: fs.readdirSync(root).map((name) => ({ name, type: "file", path: name })) };
}
function runTest(args) {
  return { ok: fs.existsSync(path.join(root, args.target)), runner: args.runner, target: args.target, exit_code: 0 };
}
process.stdin.on("data", (chunk) => {
  buffer += chunk.toString("utf8");
  const lines = buffer.split(/\r?\n/);
  buffer = lines.pop() || "";
  for (const line of lines) {
    if (!line.trim()) continue;
    const message = JSON.parse(line);
    if (message.method === "initialize") {
      send({ jsonrpc: "2.0", id: message.id, result: { protocolVersion: "2024-11-05", serverInfo: { name: "vault-workspace-mcp" } } });
    } else if (message.method === "tools/list") {
      send({ jsonrpc: "2.0", id: message.id, result: { tools: [{ name: "workspace_list" }, { name: "runtime_capabilities" }, { name: "runtime_run_test" }] } });
    } else if (message.method === "tools/call") {
      let result;
      if (message.params.name === "workspace_list") result = list();
      else if (message.params.name === "runtime_capabilities") result = { executor_readiness: { codex: { installed: true, authenticated: true, headless_ready: true } } };
      else result = runTest(message.params.arguments);
      send({ jsonrpc: "2.0", id: message.id, result: { content: [{ type: "text", text: JSON.stringify(result) }] } });
    }
  }
});

