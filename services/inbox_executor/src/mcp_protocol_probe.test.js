import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { probeMcpProtocol } from "./mcp_protocol_probe.js";

const here = path.dirname(fileURLToPath(import.meta.url));

test("probe records MCP initialize, tools/list, scoped call, and bounded validation", async () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "rts01-mcp-fixture-"));
  fs.mkdirSync(path.join(fixture, "tests"), { recursive: true });
  fs.writeFileSync(
    path.join(fixture, "tests", "fixture.test.js"),
    "import test from 'node:test'; test('fixture', () => {});\n",
    "utf8",
  );
  const result = await probeMcpProtocol({
    serverPath: path.join(here, "test-fixtures", "rts01-mcp-server.js"),
    workspaceRoot: fixture,
    auditDir: path.join(fixture, "audit"),
    trashDir: path.join(fixture, "trash"),
    tests: [{ runner: "node_test", projectDir: ".", target: "tests", timeoutSec: 30 }],
  });

  assert.equal(result.ok, true);
  assert.equal(result.evidence.initialize.ok, true);
  assert.equal(result.evidence.tools_list.ok, true);
  assert.equal(result.evidence.calls.workspace_list.ok, true);
  assert.equal(result.evidence.calls.runtime_run_test[0].ok, true);
});

