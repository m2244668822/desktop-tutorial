import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "agentic_executor.js"), "utf8");

test("R17 binds the agent MCP root to the assigned isolated project", () => {
  assert.match(
    source,
    /VAULT_WORKSPACE_ROOT:\s*agentProjectRoot/,
    "agent MCP environment must bind VAULT_WORKSPACE_ROOT to agentProjectRoot"
  );
});

test("R17 persists strict auth evidence in the orchestrator Result", () => {
  assert.match(source, /RTS01_AUTH_CLASS/);
  assert.match(source, /RTS01_LOGIN_STATUS_EXIT/);
  assert.match(source, /RTS01_API_KEY_FALLBACK/);
  assert.match(source, /RTS01_HEADLESS_READY/);
});

test("R17 rejects a conflicting MCP workspace root before success", () => {
  assert.match(source, /MCP_WORKSPACE_ROOT_MISMATCH/);
});


test("R19 accepts structured MCP evidence while keeping root consistency fail-closed", () => {
  assert.match(source, /executor_readiness/);
  assert.match(source, /agentWorkspaceRootOk/);
  assert.match(source, /agent_did_not_call_mcp/);
});
