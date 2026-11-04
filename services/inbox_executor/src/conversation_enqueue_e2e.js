import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const cli = path.join(__dirname, "conversation_enqueue.js");
const queueCli = path.join(__dirname, "queue_cli.js");
const root = fs.mkdtempSync(path.join(os.tmpdir(), "conversation-enqueue-e2e-"));

try {
  fs.mkdirSync(path.join(root, "智能體", "tasks"), { recursive: true });
  fs.writeFileSync(path.join(root, "sample.md"), "# sample\n", "utf8");

  const event = {
    event_id: "evt-local-001",
    conversation_id: "conv-local",
    turn_id: "turn-1",
    actor: "user",
    occurred_at: "2026-11-04T13:50:00+08:00",
    source_system: "chatgpt",
    text: "請讀 sample.md 並留下可驗證結果。",
    event_kind: "task_request",
    proposals: {
      user_claims: [
        {
          claim: "使用者目前優先要求可在本機實際執行。",
          claim_type: "goal",
          epistemic_status: "KNOWN",
          confidence: 1
        }
      ],
      task: {
        task_id: "local-mechanical-demo",
        task_goal: "read sample.md",
        route: "mechanical",
        executor: "auto",
        output: "checklist",
        mechanical_actions: [
          { tool: "workspace.read", args: { path: "sample.md" } }
        ]
      }
    }
  };

  const run = spawnSync(process.execPath, [cli], {
    cwd: root,
    input: JSON.stringify(event),
    encoding: "utf8",
    env: { ...process.env, VAULT_WORKSPACE_ROOT: root }
  });
  assert.equal(run.status, 0, run.stderr);
  const result = JSON.parse(run.stdout);
  assert.equal(result.ok, true);
  assert.equal(result.queued.task_id, "local-mechanical-demo");
  assert.equal(result.claim_candidates, 1);

  const eventPath = path.join(root, "智能體", "conversation-events", "evt-local-001.json");
  const taskPath = path.join(root, "智能體", "tasks", "local-mechanical-demo.md");
  assert.equal(fs.existsSync(eventPath), true);
  assert.equal(fs.existsSync(taskPath), true);

  const taskText = fs.readFileSync(taskPath, "utf8");
  assert.match(taskText, /status: queued/);
  assert.match(taskText, /route\s+mechanical/);
  assert.match(taskText, /workspace\.read/);

  const githubOutput = path.join(root, "gh-output.txt");
  fs.writeFileSync(githubOutput, "", "utf8");
  const queue = spawnSync(process.execPath, [queueCli], {
    cwd: root,
    encoding: "utf8",
    env: {
      ...process.env,
      VAULT_WORKSPACE_ROOT: root,
      GITHUB_OUTPUT: githubOutput
    }
  });
  assert.equal(queue.status, 0, queue.stderr);
  const fields = fs.readFileSync(githubOutput, "utf8");
  assert.match(fields, /task_id=local-mechanical-demo/);
  assert.match(fields, /route=mechanical/);

  console.log("CONVERSATION_ENQUEUE_E2E_PASS");
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
