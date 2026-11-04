import assert from "node:assert/strict";
import test from "node:test";
import { resolveExecutorCommand } from "../src/workspace.js";

test("explicit executor path wins over PATH lookup", () => {
  const result = resolveExecutorCommand(
    "codex",
    "C:\\Runner Tools\\codex.cmd",
    () => "C:\\PATH\\codex.cmd",
    () => true,
  );

  assert.deepEqual(result, {
    path: "C:\\Runner Tools\\codex.cmd",
    source: "explicit_override",
  });
});

test("missing explicit executor path is unavailable instead of falling back", () => {
  const result = resolveExecutorCommand(
    "codex",
    "C:\\Runner Tools\\missing-codex.cmd",
    () => "C:\\PATH\\codex.cmd",
    () => false,
  );

  assert.deepEqual(result, {
    path: "",
    source: "explicit_override_invalid",
    reason: "path_missing",
  });
});

test("empty override reports PATH discovery source", () => {
  const result = resolveExecutorCommand(
    "agent",
    "",
    () => "C:\\Cursor\\agent.cmd",
    () => true,
  );

  assert.deepEqual(result, {
    path: "C:\\Cursor\\agent.cmd",
    source: "path_lookup",
  });
});
