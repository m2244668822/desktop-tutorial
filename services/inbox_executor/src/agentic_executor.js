#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { VaultWorkspace } from "../../vault_workspace_mcp/src/workspace.js";
import {
  currentTaskEnvelope,
  readInbox,
  resolveInboxPath,
  setStatus,
  taskIdFromText,
  upsertNamedResult,
} from "./inbox.js";
import {
  executorIdentityMarkdown,
  upsertExecutorClaim,
  validateClaimResult,
} from "./executor_identity.js";
import { contractField, routeInboxTask } from "./executor_router.js";
import { normalizeProjectReference } from "./project_reference.js";
import { createRtsFixtureWorktree } from "./rts_fixture_worktree.js";
import { classifyRtsReport, fixtureServer, fixtureTools, inspectRtsAgentEvents } from "./rts_agent_evidence.js";

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

function runTool(command, args, options = {}) {
  if (process.platform !== "win32") return run(command, args, options);
  if (command === "codex" && process.env.WHITE_STUDIO_CODEX_BIN &&
      fs.existsSync(process.env.WHITE_STUDIO_CODEX_BIN)) {
    return run(process.env.WHITE_STUDIO_CODEX_BIN, args, options);
  }
  const located = run("where.exe", [command], {
    cwd: options.cwd || vaultRoot,
    timeout: 2500,
  });
  const first = String(located.stdout || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .find(Boolean) || "";
  if (/\.(?:cmd|bat)$/i.test(first)) {
    return run(
      process.env.ComSpec || "cmd.exe",
      ["/d", "/s", "/c", command, ...args],
      options
    );
  }
  return run(first || command, args, options);
}

function codexExecArgs(analysisOnly) {
  const help = runTool("codex", ["exec", "--help"], {
    cwd: vaultRoot,
    timeout: 10000,
    env: process.env,
  });
  const helpText = String(help.stdout || "") + "\n" + String(help.stderr || "");
  const args = ["exec", "--json"];

  if (helpText.includes("--ask-for-approval")) {
    args.push(
      "--sandbox",
      analysisOnly ? "read-only" : "workspace-write",
      "--ask-for-approval",
      "never"
    );
  } else if (helpText.includes("--approve-for-me")) {
    // Newer local Codex builds route approvals through automatic review and
    // reject --approve-for-me together with an explicit --sandbox flag.
    if (analysisOnly) args.push("--sandbox", "read-only");
    else args.push("--approve-for-me");
  } else {
    throw Object.assign(new Error("codex_approval_flag_unsupported"), {
      code: "codex_approval_flag_unsupported",
    });
  }

  if (helpText.includes("--ephemeral")) args.push("--ephemeral");
  return args;
}

function safeTaskName(taskId) {
  const base = String(taskId || "task")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  const suffix = crypto.createHash("sha256").update(String(taskId)).digest("hex").slice(0, 8);
  return (base || "task") + "-" + suffix;
}

function shortWorktreeName(taskId) {
  // The Vault contains long paths. Keep the human-readable task name for the
  // branch, but use a bounded key for the Windows worktree directory so the
  // checkout does not cross the legacy MAX_PATH boundary.
  const suffix = crypto.createHash("sha256").update(String(taskId)).digest("hex").slice(0, 16);
  return `w-${suffix}`;
}

function currentContract(text) {
  return currentTaskEnvelope(text).slice(0, 24000);
}

function resolveAssignedProject(project) {
  const raw = String(project || "").trim();
  if (!raw) {
    throw Object.assign(new Error("project_required"), { code: "project_required" });
  }
  const workspaceName = path.basename(vaultRoot);
  const reference = normalizeProjectReference(raw, workspaceName);
  const rel = reference.vaultRelative;
  const abs = path.resolve(vaultRoot, rel);
  const relative = path.relative(vaultRoot, abs);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw Object.assign(new Error("project_outside_workspace"), { code: "project_outside_workspace" });
  }
  if (!fs.existsSync(abs) || !fs.statSync(abs).isDirectory()) {
    throw Object.assign(new Error("project_missing"), { code: "project_missing" });
  }
  return { name: reference.name, vaultRelative: rel.replace(/\\/g, "/"), abs };
}

function loadTestProfile(projectName, { allowEmpty = false } = {}) {
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
    if (allowEmpty) return { tests: [] };
    throw Object.assign(new Error("no_test_profile"), { code: "no_test_profile" });
  }
  return profile;
}

function extractAgentOutput(stdout) {
  const raw = String(stdout || "");
  const collected = [];
  const seen = new Set();

  const add = (value) => {
    const text = String(value || "").trim();
    if (!text || seen.has(text)) return;
    seen.add(text);
    collected.push(text);
  };

  const visit = (value, key = "") => {
    if (typeof value === "string") {
      if (["text", "output_text", "message", "content", "result", "final_output"].includes(key)) {
        add(value);
      }
      return;
    }
    if (Array.isArray(value)) {
      for (const item of value) visit(item, key);
      return;
    }
    if (!value || typeof value !== "object") return;
    for (const [childKey, childValue] of Object.entries(value)) visit(childValue, childKey);
  };

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("{")) continue;
    try {
      visit(JSON.parse(trimmed));
    } catch {
      // Raw stdout fallback below.
    }
  }

  const combined = collected.join("\n\n").trim();
  const useful = combined || raw.trim();
  return useful ? useful.slice(-24000) : "";
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
  // Keep Result files compatible with git diff --check. A single trailing
  // newline is canonical; extra blank lines at EOF break publication.
  next = next.replace(/\r?\n+$/, "\n");
  fs.writeFileSync(inboxPath, next, "utf8");
}

function currentClaimState(taskId, identity) {
  if (!fs.existsSync(inboxPath)) {
    return { ok: false, code: "inbox_missing", text: "" };
  }
  const text = fs.readFileSync(inboxPath, "utf8");
  if (taskIdFromText(text) !== taskId) {
    return { ok: false, code: "task_replaced", text };
  }
  const validation = validateClaimResult(text, taskId, identity);
  if (!validation.ok) {
    return { ok: false, code: validation.code, text, validation };
  }
  return { ok: true, code: validation.code, text, validation };
}

function installFailClosedHandlers(taskId, identity, selected, evidence = []) {
  let handling = false;
  const handler = (error) => {
    if (handling) return;
    handling = true;
    const code = error?.code || "orchestration_exception";
    const message = evidence.length ? code : String(error?.stack || error?.message || error)
      .replace(/\r?\n/g, " ")
      .slice(0, 1600);
    try {
      const current = currentClaimState(taskId, identity);
      if (current.ok) {
        writeTerminalResult({
          text: current.text,
          marker: `## Result（${selected}-executor 回寫）`,
          status: "blocked",
          taskId,
          identity,
          validation: current.validation,
          details: [
            ...evidence,
            ...(error?.worktreeEvidence ? [`- worktree_failure：\`${JSON.stringify(error.worktreeEvidence)}\``] : []),
            `- code：\`${code}\``,
            "- route：`agentic`",
            `- message：${message}`,
            "- terminal_recovery：`fail_closed_exception_handler`",
          ],
        });
      } else {
        process.stderr.write(
          `agentic-executor: exception result not written because current task ownership changed: ${current.code}\n`
        );
      }
    } catch (persistError) {
      process.stderr.write(
        `agentic-executor: failed to persist terminal exception result: ${String(
          persistError?.stack || persistError
        )}\n`
      );
    }
    process.stderr.write(`agentic-executor: ${code}: ${message}\n`);
    process.exit(5);
  };
  process.on("uncaughtException", handler);
  process.on("unhandledRejection", handler);
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
const legacyRtsProbe = process.env.RTS01_MCP_PROBE_BASELINE === "1" && /^rts01-mcp-probe-\d+-baseline$/.test(taskId);
const strictAuth = contractField(initial.text, "auth_mode")?.trim().toLowerCase() === "chatgpt";
const runId = process.env.GITHUB_RUN_ID || "";
const traceId = strictAuth ? crypto.randomUUID() : "";
const leaseId = strictAuth ? crypto.randomUUID() : "";
const outputKind = String(contractField(initial.text, "Output") || "").trim().toLowerCase();
const analysisOnly = new Set(["analysis", "summary", "checklist", "proposal", "reading-layer"]).has(outputKind);

const controlWs = new VaultWorkspace({
  workspaceRoot: vaultRoot,
  auditDir: path.join(vaultRoot, "runtime", ".mcp-audit"),
  trashDir: path.join(vaultRoot, "runtime", ".mcp-trash"),
  autoApprove: false,
});
const capabilities = controlWs.runtimeCapabilities();
const decision = routeInboxTask(initial.text, capabilities, process.env);
let strictFields = [];
if (strictAuth) {
  const runtimeRevision = String(git(__dirname, ["rev-parse", "HEAD"]).stdout || "").trim();
  const apiKeyFallback = Object.keys(process.env).some(key => /^(?:CODEX|OPENAI)_API_KEY$/i.test(key));
  const login = !apiKeyFallback && /^\d+$/.test(runId)
    ? runTool("codex", ["login", "status"], { cwd: vaultRoot, timeout: 12000 })
    : {};
  const loginText = (String(login.stdout || "") + "\n" + String(login.stderr || ""))
    .replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "");
  const authClass = /^\s*Logged in using ChatGPT\s*$/im.test(loginText) ? "chatgpt" : "unverified";
  const headlessReady = capabilities.executor_readiness?.codex?.headless_ready === true;
  strictFields = [
    `- run_id：\`${runId}\``,
    `- trace_id：\`${traceId}\``,
    `- runtime_revision：\`${runtimeRevision}\``,
    `- RTS01_AUTH_CLASS：\`${authClass}\``,
    `- RTS01_LOGIN_STATUS_EXIT：\`${login.status ?? "unavailable"}\``,
    `- RTS01_API_KEY_FALLBACK：\`${apiKeyFallback}\``,
    `- RTS01_HEADLESS_READY：\`${headlessReady}\``,
  ];
  if (authClass !== "chatgpt" || login.status !== 0 || apiKeyFallback || !headlessReady ||
      decision.selected_executor !== "codex" || !/^\d+$/.test(runId) || !/^[0-9a-f]{40}$/.test(runtimeRevision)) {
    const result = [`- task_id：\`${taskId}\``, ...strictFields, "- code: strict_agentic_auth_gate_failed"].join("\n");
    const blocked = upsertNamedResult(setStatus(initial.text, "blocked"), "## Result（codex-executor 回寫）", result);
    fs.writeFileSync(inboxPath, blocked.replace(/\r?\n+$/, "\n"), "utf8");
    process.stderr.write("RTS01_STRICT_AUTH_GATE_BLOCKED before_claim=true\n");
    process.exit(4);
  }
  process.stdout.write(`RTS01_STRICT_AUTH_GATE_PASS task_id=${taskId} run_id=${runId} trace_id=${traceId}\n`);
}
if (!decision.ok || decision.route !== "agentic") {
  process.stderr.write(`agentic-executor: route rejected ${JSON.stringify(decision)}\n`);
  process.exit(4);
}

const selected = decision.selected_executor;
const identity = buildIdentity(selected, capabilities, new Date());
let running = setStatus(initial.text, "running");
running = upsertExecutorClaim(running, taskId, identity);
if (strictAuth) {
  const leaseExpires = new Date(Date.now() + (maxAgentSeconds + 540) * 1000).toISOString();
  strictFields.push(`- lease_id：\`${leaseId}\``, `- lease_expires_at：\`${leaseExpires}\``);
  running = running.replace(
    /(^## Executor Claim[^\r\n]*\r?\n)/m,
    `$1\n- run_id：\`${runId}\`\n- trace_id：\`${traceId}\`\n- lease_id：\`${leaseId}\`\n- lease_expires_at：\`${leaseExpires}\`\n`
  );
}
fs.writeFileSync(inboxPath, running, "utf8");
if (strictAuth) process.stdout.write(`RTS01_CLAIM_PERSISTED task_id=${taskId} run_id=${runId} trace_id=${traceId} lease_id=${leaseId}\n`);
installFailClosedHandlers(taskId, identity, selected, strictFields);

const project = resolveAssignedProject(contractField(initial.text, "project"));
const testProfile = loadTestProfile(project.name, { allowEmpty: analysisOnly });
if (strictAuth && (project.name !== "automation-fixture" || analysisOnly ||
    testProfile.tests.length !== 1 || testProfile.tests[0].runner !== "node_test" ||
    testProfile.tests[0].target !== "tests" || testProfile.tests[0].timeoutSec !== 60)) {
  throw Object.assign(new Error("RTS fixture profile mismatch"), { code: "rts01_fixture_profile_mismatch" });
}

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
const worktreeName = shortWorktreeName(strictAuth ? taskId + ":" + traceId : taskId);
const branchNameCandidate = "runner/" + safeName;
const refCheck = git(sourceRepoRoot, ["check-ref-format", "--branch", branchNameCandidate]);
if (refCheck.status !== 0) {
  throw Object.assign(new Error("runner_branch_invalid"), {
    code: "runner_branch_invalid",
    detail: String(refCheck.stderr || refCheck.stdout || "").slice(-1000),
  });
}

// Read-only analysis runs directly in the isolated GitHub Actions checkout.
// Creating a second Windows worktree for a no-write task adds failure surface
// (path length / checkout cost) without adding isolation. Implementation tasks
// still use a detached worktree and independent validation.
let worktreeRoot = sourceRepoRoot;
if (!analysisOnly) {
  worktreeRoot = path.join(
    process.env.RUNNER_TEMP || os.tmpdir(),
    "white-studio-worktrees",
    worktreeName
  );
  fs.mkdirSync(path.dirname(worktreeRoot), { recursive: true });
  if (strictAuth) {
    const worktreeEvidence = createRtsFixtureWorktree(sourceRepoRoot, worktreeRoot, baseSha);
    strictFields.push(`- worktree_evidence：\`${JSON.stringify(worktreeEvidence)}\``);
    console.log("RTS01_WORKTREE_PASS " + JSON.stringify(worktreeEvidence));
  } else {
    git(sourceRepoRoot, ["worktree", "remove", "--force", worktreeRoot], 60000);
    git(sourceRepoRoot, ["worktree", "prune"], 30000);
    if (fs.existsSync(worktreeRoot)) {
      fs.rmSync(worktreeRoot, { recursive: true, force: true });
    }
    const worktreeAdd = git(
      sourceRepoRoot,
      ["-c", "core.longpaths=true", "worktree", "add", "--detach", worktreeRoot, baseSha],
      180000
    );
    if (worktreeAdd.status !== 0) {
      throw Object.assign(new Error("worktree_create_failed"), {
        code: "worktree_create_failed",
        detail: String(worktreeAdd.stderr || worktreeAdd.stdout || "").slice(-1600),
      });
    }
  }
}

const agentProjectRoot = projectRelInRepo
  ? path.join(worktreeRoot, projectRelInRepo)
  : worktreeRoot;
const evidenceDir = strictAuth
  ? fs.mkdtempSync(path.join(process.env.RUNNER_TEMP || os.tmpdir(), "rts01-"))
  : "";
const mcpEvidencePath = path.join(evidenceDir, "mcp.jsonl");
const schemaPath = path.join(evidenceDir, "final.schema.json");
if (strictAuth) {
  fs.writeFileSync(schemaPath, JSON.stringify({
    type: "object",
    properties: {
      status: { type: "string", enum: ["done", "blocked"] },
      workspace_root: { type: "string" },
    },
    required: ["status", "workspace_root"],
    additionalProperties: false,
  }), "utf8");
}
const selectedFixtureServer = legacyRtsProbe ? "vault-workspace" : fixtureServer;
const mcpConfig = "mcp_servers." + selectedFixtureServer;
const mcpOverrides = strictAuth ? [
  mcpConfig + ".command=" + JSON.stringify(process.execPath),
  mcpConfig + ".args=" + JSON.stringify([path.resolve(__dirname, "../../vault_workspace_mcp/src/server.js")]),
  ...(legacyRtsProbe ? [] : [
    mcpConfig + ".required=true",
    mcpConfig + ".enabled_tools=" + JSON.stringify(fixtureTools),
    ...fixtureTools.map(tool => mcpConfig + ".tools." + tool + '.approval_mode="approve"'),
  ]),
  mcpConfig + ".env={ " + Object.entries({
    RTS01_MCP_EVIDENCE: mcpEvidencePath,
    VAULT_WORKSPACE_ROOT: agentProjectRoot,
    MCP_AUDIT_DIR: path.join(evidenceDir, "audit"),
    MCP_TRASH_DIR: path.join(evidenceDir, "trash"),
    MCP_AUTO_APPROVE: "0",
  }).map(([key, value]) => `${key} = ${JSON.stringify(value)}`).join(", ") + " }",
] : [];
const prompt = [
  "You are the selected White Studio headless executor.",
  `Executor: ${selected}`,
  `Task ID: ${taskId}`,
  `Assigned project root: ${agentProjectRoot}`,
  `Output kind: ${outputKind || "implementation"}`,
  "",
  "Rules:",
  ...(strictAuth ? [
    `- Do not write files or run shell commands. Use only the ${selectedFixtureServer} MCP server.`,
    "- Call workspace_list, runtime_capabilities, workspace_read on tests/fixture.test.js, and runtime_run_test with runner=node_test,target=tests.",
    legacyRtsProbe
      ? "- This is a read-only fixture verification. Return one JSON object with status done only if every required MCP call and bounded test succeeds, otherwise blocked, and workspace_root equal to the assigned project root. Never claim CAS or remote publication."
      : "- Set workspace_root to the exact absolute workspace_root reported by runtime_capabilities. Report status done only when every required MCP call and bounded test succeeds; otherwise report blocked. Never claim CAS or remote publication.",
  ] : []),
  ...(strictAuth ? [] : ["- Read AGENTS.md at the repository root if present."]),
  "- Work only inside the assigned repository/worktree.",
  "- Do not commit, push, merge, deploy, reset --hard, clean, force push, or modify secrets.",
  analysisOnly
    ? "- This is a read-only analysis task. Do not modify repository files. Return the complete requested deliverable in your final response."
    : strictAuth
      ? "- Keep this fixture verification read-only. Do not modify files or run shell commands."
      : "- Make the smallest change needed for the task.",
  "- You may run targeted tests, but the orchestrator will independently validate afterward when a test profile applies.",
  "- Do not modify the task contract file.",
  "- Stop after the requested deliverable; do not wait for user input.",
  "",
  "Task contract:",
  currentContract(initial.text),
].join("\n");

let agentRun;
if (selected === "codex") {
  agentRun = runTool(
    "codex",
    [...mcpOverrides.flatMap(override => ["-c", override]), ...codexExecArgs(strictAuth || analysisOnly),
      ...(strictAuth && !legacyRtsProbe ? ["--output-schema", schemaPath] : []), "-"],
    {
      cwd: agentProjectRoot,
      input: prompt,
      timeout: maxAgentSeconds * 1000,
      env: strictAuth
        ? Object.fromEntries(Object.keys(process.env)
          .filter(key => !/(?:TOKEN|API_KEY|PASSWORD|SECRET|CREDENTIAL|COOKIE)/i.test(key))
          .map(key => [key, process.env[key]]))
        : process.env,
    }
  );
} else if (selected === "cursor") {
  agentRun = runTool(
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
const agentOutput = extractAgentOutput(agentRun.stdout);

const worktreeStateRoot = path.join(
  process.env.RUNNER_TEMP || os.tmpdir(),
  "white-studio-worktree-state",
  worktreeName
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

const testsOk =
  agentOk &&
  tests.length === testProfile.tests.length &&
  tests.every((item) => item.ok && (!strictAuth || item.exit_code === 0));
const observedMcp = strictAuth && fs.existsSync(mcpEvidencePath)
  ? fs.readFileSync(mcpEvidencePath, "utf8").trim().split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line))
  : [];
const requiredMcp = ["initialize", "tools/list", "workspace.list", "runtime.capabilities", "workspace.read", "runtime.run_test"];
const observedMethods = new Set(observedMcp.filter(row => row.root === agentProjectRoot && row.outcome === "ok").map(row => row.method));
const { final, ...agentDiagnostics } = strictAuth ? inspectRtsAgentEvents(agentRun.stdout, agentRun.stderr) : {};
const report = strictAuth ? classifyRtsReport(final, agentProjectRoot, path) : null;
const reportOk = report?.root === "match";
const strictEvidenceMissing = strictAuth && (!reportOk || report.status !== "done" ||
  !requiredMcp.every(method => observedMethods.has(method)));
if (strictAuth) {
  const diagnostics = {
    ...agentDiagnostics,
    final_kind: !final ? "missing" : /^\s*(?:`{3}json\s*)?\{/.test(final) ? "json_like" : "text",
    report_root_verified: reportOk,
    report,
    server_events: observedMcp.map(({ method, outcome }) => ({ method, outcome })),
  };
  strictFields.push(`- rts_diagnostics：\`${JSON.stringify(diagnostics)}\``);
  console.log("RTS01_AGENT_DIAGNOSTICS " + JSON.stringify(diagnostics));
  strictFields.push(
    `- mcp_workspace_root：\`${agentProjectRoot}\``,
    `- mcp_methods：\`${[...observedMethods].join(" | ")}\``,
    `- evidence_digest：\`${crypto.createHash("sha256").update(JSON.stringify({
      runId, traceId, leaseId, strictFields, observedMcp, tests, agentOutputHash,
    })).digest("hex")}\``,
    `- bounded_test_results：\`${tests.map(test => `${test.runner}:${test.exit_code}`).join(" | ")}\``,
  );
  process.stdout.write(`RTS01_EXECUTION_EVIDENCE mcp=${strictEvidenceMissing ? "BLOCKED" : "PASS"} bounded_tests=${testsOk ? "PASS" : "BLOCKED"}\n`);
}

let add = { status: 0, stdout: "", stderr: "" };
let diffCheck = { status: 0, stdout: "", stderr: "" };
let stagedState = { status: 0, stdout: "", stderr: "" };
let filesChanged = [];
let readOnlyViolation = false;

if (analysisOnly) {
  // The only orchestrator-owned mutation is the task contract Claim/Result.
  // The selected agent itself runs read-only. Any other working-tree change
  // means the analysis lane violated its contract.
  const afterAgentStatus = git(sourceRepoRoot, [
    "-c",
    "core.quotepath=false",
    "status",
    "--porcelain",
  ]);
  if (afterAgentStatus.status !== 0) {
    diffCheck = { status: afterAgentStatus.status, stdout: "", stderr: "git_status_failed" };
  } else {
    const unexpected = String(afterAgentStatus.stdout || "")
      .split(/\r?\n/)
      .filter(Boolean)
      .filter((line) => {
        const rawPath = line.slice(3).trim();
        const candidate = rawPath.includes(" -> ") ? rawPath.split(" -> ").at(-1) : rawPath;
        return path.resolve(sourceRepoRoot, candidate) !== inboxAbs;
      });
    filesChanged = unexpected.slice(0, 100);
    readOnlyViolation = unexpected.length > 0;
  }
} else {
  const addArgs = projectRelInRepo
    ? ["add", "--", projectRelInRepo]
    : ["add", "--", "."];
  add = git(worktreeRoot, addArgs);
  if (add.status === 0) {
    diffCheck = git(worktreeRoot, ["diff", "--cached", "--check"]);
    stagedState = git(worktreeRoot, ["diff", "--cached", "--quiet"]);
    const changed = git(worktreeRoot, [
      "-c",
      "core.quotepath=false",
      "diff",
      "--cached",
      "--name-only",
    ]);
    filesChanged = String(changed.stdout || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 100);
  }
}

const validationOk =
  testsOk &&
  !strictEvidenceMissing &&
  add.status === 0 &&
  diffCheck.status === 0 &&
  (analysisOnly || stagedState.status === 0 || stagedState.status === 1) &&
  (!strictAuth || stagedState.status === 0) &&
  !readOnlyViolation;

let branchName = "";
let commitSha = "";
let publishOk = false;
let publishError = "";

if (validationOk) {
  const beforePublish = currentClaimState(taskId, identity);
  if (!beforePublish.ok) {
    process.stderr.write(
      `agentic-executor: publication cancelled because task ownership changed: ${beforePublish.code}\n`
    );
    process.exit(6);
  }

  const configName = git(worktreeRoot, [
    "config",
    "user.name",
    "white-studio-local-runner",
  ]);
  const configEmail = git(worktreeRoot, [
    "config",
    "user.email",
    "white-studio-local-runner@users.noreply.github.com",
  ]);
  if (analysisOnly) {
    // No product branch is created for read-only analysis. Successful agent
    // output is the artifact and will be persisted into the task Result.
    publishOk = true;
    branchName = "";
    commitSha = baseSha;
  } else if (configName.status !== 0 || configEmail.status !== 0) {
    publishError = "git_identity_config_failed";
  } else if (stagedState.status === 1) {
    const commit = git(worktreeRoot, ["commit", "-m", `runner: ${taskId}`]);
    if (commit.status === 0) {
      commitSha = String(git(worktreeRoot, ["rev-parse", "HEAD"]).stdout || "").trim();
      branchName = branchNameCandidate;
      const pushed = git(
        worktreeRoot,
        ["push", "origin", `HEAD:refs/heads/${branchName}`],
        120000
      );
      publishOk = pushed.status === 0;
      publishError = publishOk
        ? ""
        : String(pushed.stderr || pushed.stdout || "").slice(-1200);
    } else {
      publishError = String(commit.stderr || commit.stdout || "").slice(-1200);
    }
  } else if (stagedState.status === 0) {
    publishOk = true;
    branchName = "";
    commitSha = baseSha;
  } else {
    publishError = String(stagedState.stderr || "").slice(-1200);
  }
}

const currentBeforeResult = currentClaimState(taskId, identity);
if (!currentBeforeResult.ok) {
  process.stderr.write(
    `agentic-executor: Result writeback cancelled because task ownership changed: ${currentBeforeResult.code}\n`
  );
  process.exit(6);
}
const persisted = currentBeforeResult.text;
const identityValidation = currentBeforeResult.validation;
const done = validationOk && publishOk && identityValidation.ok;
const code = !agentOk
  ? "agent_execution_failed"
  : !testsOk
    ? "validation_failed"
    : strictEvidenceMissing
      ? "rts01_same_run_evidence_unverified"
    : readOnlyViolation
      ? "read_only_violation"
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
    ...strictFields,
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
    strictAuth
      ? `- agent_report_root_match：\`${reportOk}\``
      : agentOutput
      ? `- agent_output：\n\n${agentOutput.split(/\\r?\\n/).map((line) => "    " + line).join("\\n")}`
      : "- agent_output：(empty)",
    `- files_changed：\`${filesChanged.join(" | ") || "(none)"}\``,
    `- tests：\`${tests.map((item) => `${item.runner}:${item.ok ? "PASS" : "FAIL"}`).join(" | ") || "(not-run)"}\``,
    `- git_diff_check：\`${diffCheck.status === 0 ? "PASS" : "FAIL"}\``,
    publishError ? `- publish_error：${publishError.replace(/\r?\n/g, " ").slice(0, 1200)}` : "- publish_error：",
    `- worktree：\`${done ? "(cleanable)" : worktreeRoot}\``,
  ],
});

if (done && !analysisOnly) {
  git(sourceRepoRoot, ["worktree", "remove", "--force", worktreeRoot], 60000);
}

process.exit(done ? 0 : 5);
