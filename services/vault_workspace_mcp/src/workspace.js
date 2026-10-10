import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  assertAllowedPath,
  assertApproval,
  riskForTool,
} from "./permission.js";

function sha256(text) {
  return crypto.createHash("sha256").update(text, "utf8").digest("hex");
}

function unifiedDiff(filePath, before, after) {
  const a = before.split(/\r?\n/);
  const b = after.split(/\r?\n/);
  const lines = [`--- a/${filePath}`, `+++ b/${filePath}`];
  const max = Math.max(a.length, b.length);
  for (let i = 0; i < max; i++) {
    const left = a[i];
    const right = b[i];
    if (left === right) continue;
    if (left !== undefined && right === undefined) lines.push(`-${left}`);
    else if (left === undefined && right !== undefined) lines.push(`+${right}`);
    else {
      lines.push(`-${left}`);
      lines.push(`+${right}`);
    }
  }
  return lines.join("\n");
}

export class VaultWorkspace {
  constructor({
    workspaceRoot,
    auditDir,
    trashDir,
    autoApprove = false,
  }) {
    this.root = path.resolve(workspaceRoot);
    this.auditDir = path.resolve(auditDir);
    this.trashDir = path.resolve(trashDir);
    this.autoApprove = autoApprove;
    this.sessionId = crypto.randomUUID();
    fs.mkdirSync(this.auditDir, { recursive: true });
    fs.mkdirSync(this.trashDir, { recursive: true });
  }

  resolve(relOrAbs) {
    const target = path.isAbsolute(relOrAbs)
      ? path.resolve(relOrAbs)
      : path.resolve(this.root, relOrAbs);
    assertAllowedPath(this.root, target);
    return target;
  }

  rel(absPath) {
    return path.relative(this.root, absPath).split(path.sep).join("/");
  }

  audit(event) {
    const row = {
      ts: new Date().toISOString(),
      session_id: this.sessionId,
      ...event,
    };
    const line = JSON.stringify(row) + "\n";
    fs.appendFileSync(path.join(this.auditDir, "mcp-audit.jsonl"), line, "utf8");
    return row;
  }

  async list({ dir = ".", maxEntries = 200 } = {}) {
    const target = this.resolve(dir);
    const entries = await fsp.readdir(target, { withFileTypes: true });
    const out = entries.slice(0, maxEntries).map((e) => ({
      name: e.name,
      type: e.isDirectory() ? "dir" : "file",
      path: this.rel(path.join(target, e.name)),
    }));
    this.audit({ tool: "workspace.list", risk: "L0", target: this.rel(target), count: out.length });
    return { workspace_root: this.root, entries: out };
  }

  async search({ query, dir = ".", maxHits = 50 } = {}) {
    if (!query || typeof query !== "string") throw Object.assign(new Error("query_required"), { code: "query_required" });
    const start = this.resolve(dir);
    const hits = [];
    const walk = async (current) => {
      if (hits.length >= maxHits) return;
      let entries;
      try {
        entries = await fsp.readdir(current, { withFileTypes: true });
      } catch {
        return;
      }
      for (const e of entries) {
        if (hits.length >= maxHits) break;
        if (e.name === ".git" || e.name === "node_modules" || e.name === "runtime") continue;
        const full = path.join(current, e.name);
        if (e.isDirectory()) {
          await walk(full);
          continue;
        }
        if (!/\.(md|txt|json|js|cjs|mjs|ts|py|css|html)$/i.test(e.name)) continue;
        let text;
        try {
          text = await fsp.readFile(full, "utf8");
        } catch {
          continue;
        }
        if (text.includes(query)) {
          hits.push({ path: this.rel(full), preview: text.slice(0, 120) });
        }
      }
    };
    await walk(start);
    this.audit({ tool: "workspace.search", risk: "L0", query, hits: hits.length });
    return { query, hits };
  }

  async read({ path: rel }) {
    const target = this.resolve(rel);
    const content = await fsp.readFile(target, "utf8");
    const hash = sha256(content);
    this.audit({ tool: "workspace.read", risk: "L0", target: this.rel(target), hash });
    return { path: this.rel(target), content, hash };
  }

  _approvalOrAuto(level, draft) {
    if (this.autoApprove && (level === "L1" || level === "L2" || level === "L3")) {
      return {
        approved: true,
        action_id: draft.action_id,
        diff_hash: draft.diff_hash,
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
      };
    }
    return draft.approval;
  }

  async create({ path: rel, content = "", approval }) {
    const level = riskForTool("workspace.create");
    const target = this.resolve(rel);
    if (fs.existsSync(target)) {
      throw Object.assign(new Error("file_exists"), { code: "file_exists" });
    }
    const action_id = crypto.randomUUID();
    const diff = unifiedDiff(this.rel(target), "", content);
    const diff_hash = sha256(diff);
    const approved = this._approvalOrAuto(level, { action_id, diff_hash, approval });
    assertApproval(level, approved);
    if (approved.diff_hash !== diff_hash) {
      throw Object.assign(new Error("diff_hash_mismatch"), { code: "diff_hash_mismatch" });
    }
    await fsp.mkdir(path.dirname(target), { recursive: true });
    await fsp.writeFile(target, content, "utf8");
    const hash = sha256(content);
    const row = this.audit({
      tool: "workspace.create",
      risk: level,
      target: this.rel(target),
      action_id,
      diff_hash,
      hash,
      approval: approved.action_id,
    });
    return { path: this.rel(target), hash, action_id, diff_hash, audit: row };
  }

  async patch({ path: rel, content, approval }) {
    const level = riskForTool("workspace.patch");
    const target = this.resolve(rel);
    const before = await fsp.readFile(target, "utf8");
    const after = content;
    const action_id = crypto.randomUUID();
    const diff = unifiedDiff(this.rel(target), before, after);
    const diff_hash = sha256(diff);
    const draft = { action_id, diff_hash, before_hash: sha256(before), diff, approval };
    const approved = this._approvalOrAuto(level, draft);
    assertApproval(level, approved);
    if (approved.diff_hash !== diff_hash) {
      throw Object.assign(new Error("diff_hash_mismatch"), { code: "diff_hash_mismatch" });
    }
    await fsp.writeFile(target, after, "utf8");
    const hash = sha256(after);
    const row = this.audit({
      tool: "workspace.patch",
      risk: level,
      target: this.rel(target),
      action_id,
      diff_hash,
      before_hash: draft.before_hash,
      hash,
      approval: approved.action_id,
    });
    return { path: this.rel(target), hash, action_id, diff_hash, diff, audit: row };
  }

  /** Propose patch without writing — for approval flow. */
  async proposePatch({ path: rel, content }) {
    const target = this.resolve(rel);
    const before = await fsp.readFile(target, "utf8");
    const diff = unifiedDiff(this.rel(target), before, content);
    const proposal = {
      path: this.rel(target),
      before_hash: sha256(before),
      after_hash: sha256(content),
      diff,
      diff_hash: sha256(diff),
      action_id: crypto.randomUUID(),
      risk: riskForTool("workspace.patch"),
    };
    this.audit({
      tool: "workspace.propose_patch",
      risk: "L0",
      target: proposal.path,
      diff_hash: proposal.diff_hash,
      before_hash: proposal.before_hash,
      after_hash: proposal.after_hash,
    });
    return proposal;
  }

  runtimeCapabilities() {
    const locator = process.platform === "win32" ? "where.exe" : "which";
    const commands = ["git", "node", "python", "py", "code", "cursor", "agent", "codex"];
    const locations = {};
    const available = {};

    for (const command of commands) {
      const result = spawnSync(locator, [command], {
        cwd: this.root,
        encoding: "utf8",
        timeout: 2500,
        shell: false,
      });
      const located = String(result.stdout || "")
        .split(/\r?\n/)
        .map((item) => item.trim())
        .find(Boolean) || "";
      locations[command] = result.status === 0 ? located : "";
      available[command] = Boolean(locations[command]);
    }

    const probe = (command, args, timeout = 5000) => {
      const located = locations[command];
      if (!located) {
        return { installed: false, ok: false, output: "", path: "" };
      }

      const isBatchShim =
        process.platform === "win32" && /\.(?:cmd|bat)$/i.test(located);
      const executable = isBatchShim ? (process.env.ComSpec || "cmd.exe") : located;
      const executableArgs = isBatchShim
        ? ["/d", "/s", "/c", command, ...args]
        : args;
      const result = spawnSync(executable, executableArgs, {
        cwd: this.root,
        encoding: "utf8",
        timeout,
        shell: false,
        env: process.env,
      });
      const output = String(result.stdout || result.stderr || "")
        .trim()
        .split(/\r?\n/)
        .slice(0, 3)
        .join(" ");
      return {
        installed: true,
        ok: result.status === 0 && !result.error,
        output: output.slice(0, 300),
        path: located,
      };
    };

    const codexVersion = probe("codex", ["--version"], 3000);
    const codexAuth = probe("codex", ["login", "status"], 5000);
    const cursorVersion = probe("agent", ["--version"], 3000);
    const cursorAuth = probe("agent", ["status"], 5000);
    const vscodeVersion = probe("code", ["--version"], 3000);

    const payload = {
      platform: process.platform,
      workspace_root: this.root,
      commands: available,
      command_paths: locations,
      executors: {
        workspace_mcp: true,
        vscode_cli: Boolean(available.code),
        vscode_agent_host: Boolean(available.code),
        cursor_editor_cli: Boolean(available.cursor),
        cursor_agent_cli: Boolean(available.agent),
        codex_cli: Boolean(available.codex),
      },
      executor_readiness: {
        codex: {
          installed: codexVersion.installed,
          version: codexVersion.output,
          path: codexVersion.path,
          authenticated: codexAuth.ok,
          headless_ready: codexVersion.installed && codexAuth.ok,
        },
        cursor: {
          installed: cursorVersion.installed,
          version: cursorVersion.output,
          path: cursorVersion.path,
          authenticated: cursorAuth.ok,
          headless_ready: cursorVersion.installed && cursorAuth.ok,
        },
        vscode: {
          installed: vscodeVersion.installed,
          version: vscodeVersion.output,
          path: vscodeVersion.path,
          interactive_only: true,
          headless_ready: false,
        },
      },
    };

    this.audit({
      tool: "runtime.capabilities",
      risk: "L0",
      platform: payload.platform,
      executors: payload.executors,
      readiness: {
        codex: payload.executor_readiness.codex.headless_ready,
        cursor: payload.executor_readiness.cursor.headless_ready,
        vscode: payload.executor_readiness.vscode.installed,
      },
    });
    return payload;
  }

  _findCommand(candidates = []) {
    const locator = process.platform === "win32" ? "where.exe" : "which";
    for (const candidate of candidates) {
      const result = spawnSync(locator, [candidate], {
        cwd: this.root,
        encoding: "utf8",
        timeout: 2500,
      });
      if (result.status === 0) return candidate;
    }
    return "";
  }

  runTest({ runner = "pytest", target = "tests", projectDir = "", timeoutSec = 60 } = {}) {
    const safeRunner = String(runner || "pytest").trim().toLowerCase();
    const safeTimeoutMs = Math.max(
      5_000,
      Math.min(Number(timeoutSec || 60) * 1000, 120_000),
    );
    const maxOutput = 60_000;
    const normalizedProjectDir = String(projectDir || "").trim().replace(/\\/g, "/");
    const lexicalProjectRoot = normalizedProjectDir ? this.resolve(normalizedProjectDir) : this.root;
    if (!fs.existsSync(lexicalProjectRoot) || !fs.statSync(lexicalProjectRoot).isDirectory()) {
      throw Object.assign(new Error("test_project_missing"), { code: "test_project_missing" });
    }

    const workspaceReal = fs.realpathSync(this.root);
    const projectRoot = fs.realpathSync(lexicalProjectRoot);
    const projectFromWorkspace = path.relative(workspaceReal, projectRoot);
    if (projectFromWorkspace.startsWith("..") || path.isAbsolute(projectFromWorkspace)) {
      throw Object.assign(new Error("test_project_outside_workspace"), {
        code: "test_project_outside_workspace",
      });
    }

    const assertRealInProject = (candidate, code) => {
      const real = fs.realpathSync(candidate);
      const rel = path.relative(projectRoot, real);
      if (rel.startsWith("..") || path.isAbsolute(rel)) {
        throw Object.assign(new Error(code), { code });
      }
      return { real, rel: rel.replace(/\\/g, "/") };
    };

    const testEnv = {};
    for (const key of [
      "PATH",
      "Path",
      "SystemRoot",
      "WINDIR",
      "ComSpec",
      "TEMP",
      "TMP",
      "HOME",
      "USERPROFILE",
      "LOCALAPPDATA",
      "APPDATA",
      "ProgramFiles",
      "ProgramFiles(x86)",
      "NODE_PATH",
    ]) {
      if (process.env[key]) testEnv[key] = process.env[key];
    }
    testEnv.CI = "1";
    testEnv.PYTHONUNBUFFERED = "1";

    let command = "";
    let args = [];
    let normalizedTarget = String(target || "").trim().replace(/\\/g, "/");

    if (safeRunner === "static_smoke") {
      normalizedTarget = normalizedTarget || "index.html";
      const entryPath = path.resolve(projectRoot, normalizedTarget);
      if (!fs.existsSync(entryPath)) {
        throw Object.assign(new Error("static_smoke_entry_missing"), {
          code: "static_smoke_entry_missing",
        });
      }
      assertRealInProject(entryPath, "static_smoke_target_outside_project");
      const node = this._findCommand(["node"]);
      if (!node) {
        throw Object.assign(new Error("node_unavailable"), { code: "node_unavailable" });
      }
      const jsFiles = fs
        .readdirSync(projectRoot, { withFileTypes: true })
        .filter((item) => item.isFile() && item.name.endsWith(".js"))
        .map((item) => item.name)
        .slice(0, 50);
      const started = Date.now();
      const checks = [];
      let ok = true;
      for (const jsFile of jsFiles) {
        const jsPath = path.join(projectRoot, jsFile);
        assertRealInProject(jsPath, "static_smoke_target_outside_project");
        const result = spawnSync(node, ["--check", jsFile], {
          cwd: projectRoot,
          encoding: "utf8",
          timeout: safeTimeoutMs,
          shell: false,
          env: testEnv,
          maxBuffer: 2 * 1024 * 1024,
        });
        const passed = !result.error && result.status === 0;
        ok = ok && passed;
        checks.push({
          file: jsFile,
          ok: passed,
          stderr: String(result.stderr || "").slice(-4000),
        });
        if (!passed) break;
      }
      const durationMs = Date.now() - started;
      const stdoutRaw = JSON.stringify({ entry: normalizedTarget, js_checks: checks }, null, 2);
      const row = this.audit({
        tool: "runtime.run_test",
        risk: "L1",
        runner: safeRunner,
        project_dir: normalizedProjectDir,
        target: normalizedTarget,
        ok,
        exit_code: ok ? 0 : 1,
        timed_out: false,
        duration_ms: durationMs,
      });
      return {
        ok,
        runner: safeRunner,
        project_dir: normalizedProjectDir,
        target: normalizedTarget,
        command: node,
        args: ["--check", "<top-level-js-files>"],
        exit_code: ok ? 0 : 1,
        timed_out: false,
        duration_ms: durationMs,
        stdout: stdoutRaw.slice(-maxOutput),
        stderr: "",
        truncated: stdoutRaw.length > maxOutput,
        error: "",
        audit: row,
      };
    }

    if (safeRunner === "pytest") {
      normalizedTarget = normalizedTarget || "tests";
      const targetPath = path.resolve(projectRoot, normalizedTarget);
      if (!fs.existsSync(targetPath)) {
        throw Object.assign(new Error("test_target_missing"), { code: "test_target_missing" });
      }
      const targetInfo = assertRealInProject(targetPath, "test_target_outside_tests");
      if (!(targetInfo.rel === "tests" || targetInfo.rel.startsWith("tests/"))) {
        throw Object.assign(new Error("test_target_outside_tests"), {
          code: "test_target_outside_tests",
        });
      }
      command = this._findCommand(["python", "py", "python3"]);
      if (!command) {
        throw Object.assign(new Error("python_unavailable"), { code: "python_unavailable" });
      }
      args = ["-m", "pytest", "-q", "--maxfail=1", targetInfo.rel];
      normalizedTarget = targetInfo.rel;
    } else if (safeRunner === "node_e2e") {
      if (!/^services\/[A-Za-z0-9_.-]+\/src\/e2e\.js$/.test(normalizedTarget)) {
        throw Object.assign(new Error("node_e2e_target_denied"), { code: "node_e2e_target_denied" });
      }
      const targetPath = path.resolve(projectRoot, normalizedTarget);
      if (!fs.existsSync(targetPath)) {
        throw Object.assign(new Error("test_target_missing"), { code: "test_target_missing" });
      }
      const targetInfo = assertRealInProject(targetPath, "node_e2e_target_outside_project");
      command = this._findCommand(["node"]);
      if (!command) {
        throw Object.assign(new Error("node_unavailable"), { code: "node_unavailable" });
      }
      args = [targetInfo.rel];
      normalizedTarget = targetInfo.rel;
    } else if (safeRunner === "node_test") {
      normalizedTarget = normalizedTarget || "tests";
      const targetPath = path.resolve(projectRoot, normalizedTarget);
      if (!fs.existsSync(targetPath)) {
        throw Object.assign(new Error("test_target_missing"), { code: "test_target_missing" });
      }
      const targetInfo = assertRealInProject(targetPath, "node_test_target_outside_project");
      if (!(targetInfo.rel === "tests" || targetInfo.rel.startsWith("tests/"))) {
        throw Object.assign(new Error("node_test_target_denied"), { code: "node_test_target_denied" });
      }
      command = this._findCommand(["node"]);
      if (!command) {
        throw Object.assign(new Error("node_unavailable"), { code: "node_unavailable" });
      }

      const testFiles = [];
      const collect = (dir) => {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          if (testFiles.length >= 200) break;
          const candidate = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            collect(candidate);
            continue;
          }
          if (!entry.isFile() || !/\.test\.(?:c|m)?js$/i.test(entry.name)) continue;
          const info = assertRealInProject(candidate, "node_test_target_outside_project");
          testFiles.push(info.rel);
        }
      };

      if (fs.statSync(targetPath).isDirectory()) {
        collect(targetPath);
      } else if (/\.test\.(?:c|m)?js$/i.test(path.basename(targetPath))) {
        testFiles.push(targetInfo.rel);
      } else {
        throw Object.assign(new Error("node_test_target_denied"), {
          code: "node_test_target_denied",
        });
      }

      if (testFiles.length === 0) {
        throw Object.assign(new Error("node_test_files_missing"), {
          code: "node_test_files_missing",
        });
      }
      args = ["--test", ...testFiles];
      normalizedTarget = targetInfo.rel;
    } else {
      throw Object.assign(new Error("test_runner_denied"), { code: "test_runner_denied" });
    }

    const started = Date.now();
    const result = spawnSync(command, args, {
      cwd: projectRoot,
      encoding: "utf8",
      timeout: safeTimeoutMs,
      shell: false,
      env: testEnv,
      maxBuffer: 2 * 1024 * 1024,
    });
    const durationMs = Date.now() - started;
    const stdoutRaw = String(result.stdout || "");
    const stderrRaw = String(result.stderr || "");
    const stdout = stdoutRaw.slice(-maxOutput);
    const stderr = stderrRaw.slice(-maxOutput);
    const timedOut = Boolean(
      result.error &&
        (result.error.code === "ETIMEDOUT" ||
          result.error.code === "ERR_CHILD_PROCESS_STDIO_MAXBUFFER")
    );
    const exitCode = Number.isInteger(result.status) ? result.status : null;
    const ok = !result.error && exitCode === 0;

    const row = this.audit({
      tool: "runtime.run_test",
      risk: "L1",
      runner: safeRunner,
      project_dir: normalizedProjectDir,
      target: normalizedTarget,
      ok,
      exit_code: exitCode,
      timed_out: timedOut,
      duration_ms: durationMs,
    });

    return {
      ok,
      runner: safeRunner,
      project_dir: normalizedProjectDir,
      target: normalizedTarget,
      command,
      args,
      exit_code: exitCode,
      timed_out: timedOut,
      duration_ms: durationMs,
      stdout,
      stderr,
      truncated: stdoutRaw.length > maxOutput || stderrRaw.length > maxOutput,
      error: result.error ? String(result.error.message || result.error) : "",
      audit: row,
    };
  }

  async trevorWebSearch({ query, limit = 5 } = {}) {
    const safeQuery = String(query || "").trim();
    if (!safeQuery) {
      throw Object.assign(new Error("query_required"), { code: "query_required" });
    }
    const safeLimit = Math.max(1, Math.min(Number(limit) || 5, 10));
    const baseUrl = String(
      process.env.TREVOR_BASE_URL || "http://127.0.0.1:5001"
    ).replace(/\/+$/, "");
    const token = String(process.env.TREVOR_API_TOKEN || "").trim();
    const headers = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10_000);
    let response;
    try {
      response = await fetch(`${baseUrl}/api/trevor/search`, {
        method: "POST",
        headers,
        body: JSON.stringify({ query: safeQuery, limit: safeLimit }),
        signal: controller.signal,
      });
    } catch (error) {
      const err = Object.assign(
        new Error(error?.name === "AbortError" ? "trevor_search_timeout" : "trevor_search_unavailable"),
        { code: error?.name === "AbortError" ? "trevor_search_timeout" : "trevor_search_unavailable" }
      );
      throw err;
    } finally {
      clearTimeout(timer);
    }

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok || payload?.ok === false) {
      throw Object.assign(
        new Error(String(payload?.error || `trevor_search_http_${response.status}`)),
        { code: String(payload?.error || "trevor_search_failed") }
      );
    }
    const results = Array.isArray(payload.results) ? payload.results.slice(0, safeLimit) : [];
    this.audit({
      tool: "trevor.web_search",
      risk: "L1",
      query_hash: sha256(safeQuery),
      result_count: results.length,
      source: String(payload.source || ""),
    });
    return {
      ok: true,
      query: String(payload.query || safeQuery),
      source: String(payload.source || "trevor"),
      redaction_count: Number(payload.redaction_count || 0),
      results,
    };
  }

  async move({ from, to, approval }) {
    const level = riskForTool("workspace.move");
    const src = this.resolve(from);
    const dst = this.resolve(to);
    const action_id = crypto.randomUUID();
    const diff_hash = sha256(`${this.rel(src)}=>${this.rel(dst)}`);
    const approved = this._approvalOrAuto(level, { action_id, diff_hash, approval });
    assertApproval(level, approved);
    await fsp.mkdir(path.dirname(dst), { recursive: true });
    await fsp.rename(src, dst);
    const row = this.audit({
      tool: "workspace.move",
      risk: level,
      from: this.rel(src),
      to: this.rel(dst),
      action_id,
      diff_hash,
    });
    return { from: this.rel(src), to: this.rel(dst), action_id, audit: row };
  }

  async trash({ path: rel, approval }) {
    const level = riskForTool("workspace.trash");
    const src = this.resolve(rel);
    const action_id = crypto.randomUUID();
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const dest = path.join(this.trashDir, `${stamp}__${path.basename(src)}`);
    const diff_hash = sha256(`${this.rel(src)}=>trash:${dest}`);
    const approved = this._approvalOrAuto(level, { action_id, diff_hash, approval });
    assertApproval(level, approved);
    await fsp.rename(src, dest);
    const row = this.audit({
      tool: "workspace.trash",
      risk: level,
      from: this.rel(src),
      trash_path: dest,
      action_id,
      diff_hash,
    });
    return { from: this.rel(src), trash_path: dest, action_id, audit: row };
  }

}

export const TOOL_DEFS = [
  {
    name: "workspace.list",
    description: "List entries under vault workspace (scoped).",
    inputSchema: {
      type: "object",
      properties: {
        dir: { type: "string" },
        maxEntries: { type: "number" },
      },
    },
  },
  {
    name: "workspace.search",
    description: "Search text under vault workspace.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        dir: { type: "string" },
        maxHits: { type: "number" },
      },
      required: ["query"],
    },
  },
  {
    name: "workspace.read",
    description: "Read a UTF-8 file under vault workspace.",
    inputSchema: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
    },
  },
  {
    name: "workspace.propose_patch",
    description: "Generate a diff/hash proposal without writing. Use before workspace.patch.",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string" },
        content: { type: "string" },
      },
      required: ["path", "content"],
    },
  },
  {
    name: "runtime.capabilities",
    description: "Inspect which local editor/agent CLIs are available without executing them.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "runtime.run_test",
    description: "Run a bounded repository test only. Supports pytest, service-owned node E2E, fixed node --test, and static smoke checks with sanitized test environments; no repository-controlled shell scripts.",
    inputSchema: {
      type: "object",
      properties: {
        runner: { type: "string", enum: ["pytest", "node_e2e", "node_test", "static_smoke"] },
        target: { type: "string" },
        projectDir: { type: "string" },
        timeoutSec: { type: "number" },
      },
    },
  },
  {
    name: "trevor.web_search",
    description: "Search the web through Trevor's privacy-sanitized local search adapter. Prefer official sources for tool discovery.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        limit: { type: "number" },
      },
      required: ["query"],
    },
  },
  {
    name: "workspace.create",
    description: "Create a new file. L1+ may need approval.",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string" },
        content: { type: "string" },
        approval: { type: "object" },
      },
      required: ["path"],
    },
  },
  {
    name: "workspace.patch",
    description: "Replace file content with approval + diff_hash.",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string" },
        content: { type: "string" },
        approval: { type: "object" },
      },
      required: ["path", "content"],
    },
  },
  {
    name: "workspace.move",
    description: "Move/rename within workspace.",
    inputSchema: {
      type: "object",
      properties: {
        from: { type: "string" },
        to: { type: "string" },
        approval: { type: "object" },
      },
      required: ["from", "to"],
    },
  },
  {
    name: "workspace.trash",
    description: "Soft-delete into .mcp-trash (no permanent delete).",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string" },
        approval: { type: "object" },
      },
      required: ["path"],
    },
  },
];

export async function dispatch(ws, name, args = {}) {
  switch (name) {
    case "workspace.list":
      return ws.list(args);
    case "workspace.search":
      return ws.search(args);
    case "workspace.read":
      return ws.read(args);
    case "workspace.propose_patch":
      return ws.proposePatch(args);
    case "runtime.capabilities":
      return ws.runtimeCapabilities(args);
    case "runtime.run_test":
      return ws.runTest(args);
    case "trevor.web_search":
      return ws.trevorWebSearch(args);
    case "workspace.create":
      return ws.create(args);
    case "workspace.patch":
      return ws.patch(args);
    case "workspace.move":
      return ws.move(args);
    case "workspace.trash":
      return ws.trash(args);
    default:
      throw Object.assign(new Error("unknown_tool"), { code: "unknown_tool", name });
  }
}
