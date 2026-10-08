#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { VaultWorkspace } from "../../vault_workspace_mcp/src/workspace.js";
import {
  readInbox,
  resolveInboxPath,
  setStatus,
  taskIdFromText,
  topLevelSections,
  upsertNamedResult,
} from "./inbox.js";
import {
  executorIdentityMarkdown,
  upsertExecutorClaim,
  validateClaimResult,
} from "./executor_identity.js";
import { contractField, routeInboxTask } from "./executor_router.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);
const inboxPath = process.env.INBOX_PATH || resolveInboxPath(vaultRoot);
const maxAgentSeconds = Math.max(
  60,
  Math.min(Number(process.env.WHITE_STUDIO_AGENT_TIMEOUT_SEC || 1200), 1800)
);

function run(command, args, options = {}) {
  return spawnSync(command, args, {
    encoding: "utf8",
    shell: false,
    maxBuffer: 8 * 1024 * 1024,
    ...options,
  });
}

function git(cwd, args, timeout = 30000) {
  return run("git", args, { cwd, timeout });
}

function safeTaskName(taskId) {
  const base = String(taskId || "task")
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  const suffix = crypto.createHash("sha256").update(String(taskId)).digest("hex").slice(0, 8);
  return (base || "task") + "-" + suffix;
}

function currentContract(text) {
  const section = topLevelSections(text).find(
    (item) => item.heading === "## 現在這一份契約"
  );
  return (section?.text || String(text || "")).slice(0, 24000);
}

function resolveAssignedProject(project) {
  const raw = String(project || "").trim();
  if (!raw) {
    throw Object.assign(new Error("project_required"), { code: "project_required" });
  }
  const rel = raw === "desktop-tutorial" ? "runtime/desktop-tutorial" : raw;
  const abs = path.resolve(vaultRoot, rel);
  const relative = path.relative(vaultRoot, abs);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw Object.assign(new Error("project_outside_workspace"), { code: "project_outside_workspace" });
  }
  if (!fs.existsSync(abs) || !fs.statSync(abs).isDirectory()) {
    throw Object.assign(new Error("project_missing"), { code: "project_missing" });
  }
  return { name: raw, vaultRelative: rel.replace(/\\/g, "/"), abs };
}

function loadTestProfile(projectName) {
  const profilePath = path.join(vaultRoot, "runtime", "test-profiles.json");
  if (!fs.existsSync(profilePath)) {
    throw Object.assign(new Error("test_profiles_missing"), { code: "test_profiles_missing" });
  }
  let data;
  try {
    data = JSON.parse(fs.readFileSync(profilePath, "utf8"));
  } catch {
    throw Object.assign(new Error("test_profiles_invalid"), { code: "test_profiles_invalid" });
  }
  const profile = data?.projects?.[projectName];
  if (!profile || !Array.isArray(profile.tests) || profile.tests.length === 0) {
    throw Object.assign(new Error("no_test_profile"), { code: "no_test_profile" });
  }
  return profile;
}

function buildIdentity(selected, capabilities, now) {
  const readiness = capabilities?.executor_readiness?.[selected] || {};
  return {
    executor_id: selected,
    executor_type: "external",
    executor_provider: selected === "codex" ? "openai" : "cursor",
    executor_product: selected === "codex" ? "codex-cli" : "cursor-agent-cli",
    executor_mode: "github-actions-headless",
    executor_version: String(readiness.version || "unknown"),
    executor_capabilities: [
      "workspace-filesystem",
      "git-worktree",
      "bounded-command-execution",
      "bounded-tests",
      "vault-workspace-mcp",
    ],
    claimed_at: now.toISOString(),
  };
}

function writeTerminalResult({ text, marker, status, taskId, identity, validation, details }) {
  const resultMarkdown = [
    `- task_id：\`${taskId}\``,
    `- 結果：${status}`,
    executorIdentityMarkdown(identity, validation),
    ...details,
  ].join("\n");
  let next = setStatus(text, status === "done" ? "done" : "blocked");
  next = upsertNamedResult(next, marker, resultMarkdown);
  fs.writeFileSync(inboxPath, next, "utf8");
}

if (!fs.existsSync(inboxPath)) {
  process.stderr.write(`agentic-executor: missing inbox ${inboxPath}\n`);
  process.exit(2);
}

const initial = readInbox(inboxPath);
if (initial.status !== "queued") {
  process.stderr.write(`agentic-executor: inbox status=${initial.status}, nothing to do\n`);
  process.exit(0);
}

const taskId = taskIdFromText(initial.text);
const project = resolveAssignedProject(contractField(initial.text, "project"));
const testProfile = loadTestProfile(project.name);

const controlWs = new VaultWorkspace({
  workspaceRoot: vaultRoot,
  auditDir: path.join(vaultRoot, "runtime", ".mcp-audit"),
  trashDir: path.join(vaultRoot, "runtime", ".mcp-trash"),
  autoApprove: false,
});
const capabilities = controlWs.runtimeCapabilities();
const decision = routeInboxTask(initial.text, capabilities, process.env);
if (!decision.ok || decision.route !== "agentic") {
  process.stderr.write(`agentic-executor: route rejected ${JSON.stringify(decision)}\n`);
  process.exit(4);
}

const selected = decision.selected_executor;
const identity = buildIdentity(selected, capabilities, new Date());
let running = setStatus(initial.text, "running");
running = upsertExecutorClaim(running, taskId, identity);
fs.writeFileSync(inboxPath, running, "utf8");

const repoRootResult = git(project.abs, ["rev-parse", "--show-toplevel"]);
if (repoRootResult.status !== 0) {
  throw Object.assign(new Error("project_not_git_repo"), { code: "project_not_git_repo" });
}
const sourceRepoRoot = path.resolve(String(repoRootResult.stdout || "").trim());
const projectRelInRepo = path.relative(sourceRepoRoot, project.abs).replace(/\\/g, "/");
const baseShaResult = git(sourceRepoRoot, ["rev-parse", "HEAD"]);
const baseSha = String(baseShaResult.stdout || "").trim();
const sourceStatus = git(sourceRepoRoot, [
  "-c",
  "core.quotepath=false",
  "status",
  "--porcelain",
]);
if (sourceStatus.status !== 0) {
  throw Object.assign(new Error("git_status_failed"), { code: "git_status_failed" });
}
const inboxAbs = path.resolve(inboxPath);
const conflictingLines = String(sourceStatus.stdout || "")
  .split(/\r?\n/)
  .filter(Boolean)
  .filter((line) => {
    const rawPath = line.slice(3).trim();
    const candidate = rawPath.includes(" -> ") ? rawPath.split(" -> ").at(-1) : rawPath;
    return path.resolve(sourceRepoRoot, candidate) !== inboxAbs;
  });
if (conflictingLines.length > 0) {
  throw Object.assign(new Error("workspace_conflict"), {
    code: "workspace_conflict",
    conflicts: conflictingLines.slice(0, 50),
  });
}

const safeName = safeTaskName(taskId);
const worktreeRoot = path.join(
  process.env.RUNNER_TEMP || os.tmpdir(),
  "white-studio-worktrees",
  safeName
);
fs.mkdirSync(path.dirname(worktreeRoot), { recursive: true });
if (fs.existsSync(worktreeRoot)) {
  fs.rmSync(worktreeRoot, { recursive: true, force: true });
}
const worktreeAdd = git(sourceRepoRoot, ["worktree", "add", "--detach", worktreeRoot, baseSha], 60000);
if (worktreeAdd.status !== 0) {
  throw Object.assign(new Error("worktree_create_failed"), {
    code: "worktree_create_failed",
    detail: String(worktreeAdd.stderr || "").slice(-1000),
  });
}

const agentProjectRoot = projectRelInRepo
  ? path.join(worktreeRoot, projectRelInRepo)
  : worktreeRoot;
const prompt = [
  "You are the selected White Studio headless coding executor.",
  `Executor: ${selected}`,
  `Task ID: ${taskId}`,
  `Assigned project root: ${agentProjectRoot}`,
  "",
  "Rules:",
  "- Read AGENTS.md at the repository root if present.",
  "- Work only inside the assigned repository/worktree.",
  "- Do not commit, push, merge, deploy, reset --hard, clean, force push, or modify secrets.",
  "- Make the smallest change needed for the task.",
  "- You may run targeted tests, but the orchestrator will independently validate afterward.",
  "- Do not modify chatgpt-inbox.md.",
  "- Stop after implementation; do not wait for user input.",
  "",
  "Task contract:",
  currentContract(initial.text),
].join("\n");

let agentRun;
if (selected === "codex") {
  agentRun = run(
    "codex",
    ["exec", "--json", "--sandbox", "workspace-write", "--ask-for-approval", "never", "-"],
    {
      cwd: agentProjectRoot,
      input: prompt,
      timeout: maxAgentSeconds * 1000,
      env: process.env,
    }
  );
} else if (selected === "cursor") {
  agentRun = run(
    "agent",
    [
      "-p",
      "--workspace",
      agentProjectRoot,
      "--output-format",
      "json",
      "--sandbox",
      "enabled",
      prompt,
    ],
    { cwd: agentProjectRoot, timeout: maxAgentSeconds * 1000, env: process.env }
  );
} else {
  throw Object.assign(new Error("executor_not_supported"), { code: "executor_not_supported" });
}

const agentOk = !agentRun.error && agentRun.status === 0;
const agentOutputHash = crypto
  .createHash("sha256")
  .update(String(agentRun.stdout || "") + "\n" + String(agentRun.stderr || ""))
  .digest("hex");

const worktreeStateRoot = path.join(
  process.env.RUNNER_TEMP || os.tmpdir(),
  "white-studio-worktree-state",
  safeName
);
const worktreeWs = new VaultWorkspace({
  workspaceRoot: worktreeRoot,
  auditDir: path.join(worktreeStateRoot, ".mcp-audit"),
  trashDir: path.join(worktreeStateRoot, ".mcp-trash"),
  autoApprove: false,
});
const tests = [];
if (agentOk) {
  for (const test of testProfile.tests) {
    const result = worktreeWs.runTest({
      runner: test.runner,
      target: test.target,
      projectDir: projectRelInRepo,
      timeoutSec: test.timeoutSec,
    });
    tests.push({
      runner: result.runner,
      target: result.target,
      ok: result.ok,
      exit_code: result.exit_code,
      timed_out: result.timed_out,
      duration_ms: result.duration_ms,
    });
    if (!result.ok) break;
  }
}

const diffCheck = git(worktreeRoot, ["diff", "--check"]);
const testsOk = agentOk && tests.length === testProfile.tests.length && tests.every((item) => item.ok);
const validationOk = testsOk && diffCheck.status === 0;

const changedBeforeCommit = git(worktreeRoot, [
  "-c",
  "core.quotepath=false",
  "status",
  "--short",
]);
const filesChanged = String(changedBeforeCommit.stdout || "")
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter(Boolean)
  .slice(0, 100);

let branchName = "";
let commitSha = "";
let publishOk = false;
let publishError = "";
if (validationOk) {
  git(worktreeRoot, ["config", "user.name", "white-studio-local-runner"]);
  git(worktreeRoot, [
    "config",
    "user.email",
    "white-studio-local-runner@users.noreply.github.com",
  ]);
  const addArgs = projectRelInRepo ? ["add", "--", projectRelInRepo] : ["add", "--", "."];
  const add = git(worktreeRoot, addArgs);
  if (add.status === 0) {
    const staged = git(worktreeRoot, ["diff", "--cached", "--quiet"]);
    if (staged.status === 1) {
      const commit = git(worktreeRoot, ["commit", "-m", `runner: ${taskId}`]);
      if (commit.status === 0) {
        commitSha = String(git(worktreeRoot, ["rev-parse", "HEAD"]).stdout || "").trim();
        branchName = "runner/" + safeName;
        const pushed = git(
          worktreeRoot,
          ["push", "origin", `HEAD:refs/heads/${branchName}`],
          120000
        );
        publishOk = pushed.status === 0;
        publishError = publishOk ? "" : String(pushed.stderr || pushed.stdout || "").slice(-1200);
      } else {
        publishError = String(commit.stderr || commit.stdout || "").slice(-1200);
      }
    } else if (staged.status === 0) {
      publishOk = true;
      branchName = "";
      commitSha = baseSha;
    } else {
      publishError = String(staged.stderr || "").slice(-1200);
    }
  } else {
    publishError = String(add.stderr || "").slice(-1200);
  }
}

const persisted = fs.readFileSync(inboxPath, "utf8");
const identityValidation = validateClaimResult(persisted, taskId, identity);
const done = validationOk && publishOk && identityValidation.ok;
const code = !agentOk
  ? "agent_execution_failed"
  : !testsOk
    ? "validation_failed"
    : diffCheck.status !== 0
      ? "diff_check_failed"
      : !publishOk
        ? "publish_failed"
        : !identityValidation.ok
          ? identityValidation.code
          : "done";

writeTerminalResult({
  text: persisted,
  marker: `## Result（${selected}-executor 回寫）`,
  status: done ? "done" : "blocked",
  taskId,
  identity,
  validation: identityValidation,
  details: [
    `- route：\`${decision.route}\``,
    `- requested_executor：\`${decision.requested_executor}\``,
    `- selected_executor：\`${selected}\``,
    `- project：\`${project.name}\``,
    `- base_sha：\`${baseSha}\``,
    `- branch：\`${branchName || "(no-change)"}\``,
    `- commit：\`${commitSha || ""}\``,
    `- code：\`${code}\``,
    `- agent_exit_code：${Number.isInteger(agentRun.status) ? agentRun.status : "null"}`,
    `- agent_output_sha256：\`${agentOutputHash}\``,
    `- files_changed：\`${filesChanged.join(" | ") || "(none)"}\``,
    `- tests：\`${tests.map((item) => `${item.runner}:${item.ok ? "PASS" : "FAIL"}`).join(" | ") || "(not-run)"}\``,
    `- git_diff_check：\`${diffCheck.status === 0 ? "PASS" : "FAIL"}\``,
    publishError ? `- publish_error：${publishError.replace(/\r?\n/g, " ").slice(0, 1200)}` : "- publish_error：",
    `- worktree：\`${done ? "(cleanable)" : worktreeRoot}\``,
  ],
});

if (done) {
  git(sourceRepoRoot, ["worktree", "remove", "--force", worktreeRoot], 60000);
}

process.exit(done ? 0 : 5);
