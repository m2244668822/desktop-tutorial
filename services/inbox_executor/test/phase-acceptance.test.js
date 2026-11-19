import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const entry = fileURLToPath(new URL("../src/phase_acceptance.js", import.meta.url));

test("Phase A-E writes a fresh bounded fixture report with CI provenance", () => {
  const output = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "phase-report-test-")), "phase.json");
  const result = spawnSync(process.execPath, [entry, "--output", output], {
    encoding: "utf8",
    timeout: 10000,
    env: {
      ...process.env,
      GITHUB_SHA: "fixture-workspace-sha",
      GITHUB_RUN_ID: "42",
      GITHUB_RUN_ATTEMPT: "2",
      WHITE_STUDIO_RUNTIME_SHA: "fixture-runtime-sha",
    },
  });

  assert.equal(result.status, 0, result.stderr || result.stdout);
  const report = JSON.parse(fs.readFileSync(output, "utf8"));
  assert.deepEqual(report, JSON.parse(result.stdout));
  assert.equal(report.kind, "windows_phase_a_e_acceptance");
  assert.equal(report.overall, "PASS");
  assert.deepEqual(report.phases.map(({ name, status }) => [name, status]), [
    ["A", "pass"],
    ["B", "pass"],
    ["C", "pass"],
    ["D", "pass"],
    ["E", "pass"],
  ]);
  assert.deepEqual(report.provenance, {
    workspace_sha: "fixture-workspace-sha",
    runtime_sha: "fixture-runtime-sha",
    run_id: "42",
    run_attempt: "2",
  });
  assert.match(report.scope, /isolated disposable fixture/);
});
