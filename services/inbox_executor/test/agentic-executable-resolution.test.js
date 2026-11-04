import assert from "node:assert/strict";
import test from "node:test";
import { resolveToolInvocation } from "../src/executor_command.js";

test("Codex invocation uses the explicit Windows executable path", () => {
  const result = resolveToolInvocation(
    "codex",
    ["exec", "--json"],
    {
      WHITE_STUDIO_CODEX_PATH: "C:\\Runner Tools\\codex.cmd",
      ComSpec: "C:\\Windows\\System32\\cmd.exe",
    },
    () => "C:\\PATH\\codex.cmd",
    () => true,
  );

  assert.equal(result.source, "explicit_override");
  assert.equal(result.executable, "C:\\Windows\\System32\\cmd.exe");
  assert.deepEqual(result.args, [
    "/d",
    "/s",
    "/c",
    "C:\\Runner Tools\\codex.cmd",
    "exec",
    "--json",
  ]);
});

test("Cursor invocation keeps PATH behavior when no override is set", () => {
  const result = resolveToolInvocation(
    "agent",
    ["--version"],
    { ComSpec: "C:\\Windows\\System32\\cmd.exe" },
    () => "C:\\Cursor\\agent.cmd",
    () => true,
  );

  assert.equal(result.source, "path_lookup");
  assert.equal(result.executable, "C:\\Windows\\System32\\cmd.exe");
  assert.deepEqual(result.args, [
    "/d",
    "/s",
    "/c",
    "C:\\Cursor\\agent.cmd",
    "--version",
  ]);
});
