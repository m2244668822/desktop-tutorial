import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const queueCli = path.join(__dirname, "queue_cli.js");
const root = fs.mkdtempSync(path.join(os.tmpdir(), "white-studio-queue-e2e-"));

function task(taskId, priority, sample) {
  return `---
status: queued
created: 2026-10-11T00:00:00+08:00
---

## 現在這一份契約

\`\`\`text
task_id       ${taskId}
route         mechanical
executor      auto
priority      ${priority}
Goal          read a sample
Output        checklist
Done          action succeeds
\`\`\`

## Mechanical Actions

\`\`\`json
{"actions":[{"tool":"workspace.read","args":{"path":"${sample}"}}]}
\`\`\`
`;
}

function runQueue() {
  const out = path.join(root, "github-output.txt");
  fs.writeFileSync(out, "", "utf8");
  const run = spawnSync(process.execPath, [queueCli], {
    cwd: root,
    encoding: "utf8",
    env: {
      ...process.env,
      VAULT_WORKSPACE_ROOT: root,
      GITHUB_OUTPUT: out,
    },
  });
  assert.equal(run.status, 0, run.stderr);
  const outputs = Object.fromEntries(
    fs.readFileSync(out, "utf8")
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => {
        const at = line.indexOf("=");
        return [line.slice(0, at), line.slice(at + 1)];
      })
  );
  return { run, outputs };
}

try {
  const tasks = path.join(root, "智能體", "tasks");
  fs.mkdirSync(tasks, { recursive: true });
  fs.writeFileSync(path.join(root, "high.md"), "# high\n", "utf8");
  fs.writeFileSync(path.join(root, "low.md"), "# low\n", "utf8");
  fs.writeFileSync(path.join(tasks, "low.md"), task("queue-low", "low", "low.md"), "utf8");
  fs.writeFileSync(path.join(tasks, "high.md"), task("queue-high", "high", "high.md"), "utf8");

  const first = runQueue();
  assert.equal(first.outputs.ok, "true");
  assert.equal(first.outputs.task_id, "queue-high");
  assert.equal(first.outputs.route, "mechanical");
  assert.equal(
    Buffer.from(first.outputs.task_path_b64, "base64").toString("utf8").replace(/\\/g, "/"),
    "智能體/tasks/high.md"
  );

  const highPath = path.join(tasks, "high.md");
  fs.writeFileSync(
    highPath,
    fs.readFileSync(highPath, "utf8").replace("status: queued", "status: done"),
    "utf8"
  );

  const second = runQueue();
  assert.equal(second.outputs.task_id, "queue-low");
  console.log("QUEUE_E2E_PASS");
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
