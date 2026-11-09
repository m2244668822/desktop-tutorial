import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import * as workspaceModule from "./workspace.js";

test("Windows command resolution preserves Unicode PATH entries", async (t) => {
  const root = await mkdtemp(path.join(tmpdir(), "vault-mcp-路徑-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const bin = path.join(root, "工具");
  const executable = path.join(bin, "codex.exe");
  await mkdir(bin, { recursive: true });
  await writeFile(executable, "fake executable");

  const resolved = typeof workspaceModule.resolveCommandLocation === "function"
    ? workspaceModule.resolveCommandLocation("codex", {
      platform: "win32",
      env: { Path: bin, PATHEXT: ".COM;.EXE;.BAT;.CMD" },
    })
    : undefined;

  assert.equal(resolved, executable);
});
