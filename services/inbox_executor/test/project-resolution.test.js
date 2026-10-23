import assert from "node:assert/strict";
import test from "node:test";
import { resolveProjectRelativePath } from "../src/project_resolution.js";

test("registered automation fixture resolves to its disposable root", () => {
  assert.equal(
    resolveProjectRelativePath("automation-fixture", "obsidian-vault-refactor-2026-09-08"),
    "runtime/.mcp-automation-fixture"
  );
  assert.equal(
    resolveProjectRelativePath("desktop-tutorial", "obsidian-vault-refactor-2026-09-08"),
    "runtime/desktop-tutorial"
  );
});
