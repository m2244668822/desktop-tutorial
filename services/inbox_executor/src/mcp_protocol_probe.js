import { spawn } from "node:child_process";
import fs from "node:fs";

function redactDiagnostic(value) {
  return String(value || "")
    .replace(/(api[_-]?key|token|password|secret)(\s*[=:]\s*)\S+/gi, "$1$2[REDACTED]")
    .slice(-2000);
}

function parseToolResult(message, method) {
  if (!message?.result || message.result.isError) {
    throw Object.assign(new Error(`mcp_${method}_failed`), { code: `mcp_${method}_failed` });
  }
  const text = message.result.content?.[0]?.text;
  if (typeof text !== "string") {
    throw Object.assign(new Error(`mcp_${method}_payload_invalid`), {
      code: `mcp_${method}_payload_invalid`,
    });
  }
  try {
    return JSON.parse(text);
  } catch {
    throw Object.assign(new Error(`mcp_${method}_payload_invalid`), {
      code: `mcp_${method}_payload_invalid`,
    });
  }
}

function normalizeProbeError(error, fallbackCode) {
  const code = String(error?.code || "").trim();
  if (code.startsWith("mcp_")) {
    return Object.assign(new Error(code), { code });
  }
  return Object.assign(new Error(fallbackCode), { code: fallbackCode });
}

function request(child, pending, sequence, method, params = {}, diagnostics, timeoutMs = 5000) {
  const id = sequence.next++;
  diagnostics.last_method = method;
  diagnostics.stage = method;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(Object.assign(new Error("mcp_" + method + "_timeout"), {
        code: "mcp_" + method + "_timeout",
      }));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer });
    try {
      child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
    } catch (error) {
      clearTimeout(timer);
      pending.delete(id);
      reject(normalizeProbeError(error, "mcp_transport_write_failed"));
    }
  });
}

export async function probeMcpProtocol({
  serverPath,
  workspaceRoot,
  auditDir,
  trashDir,
  tests = [],
  env = process.env,
} = {}) {
  const pending = new Map();
  const sequence = { next: 1 };
  const diagnostics = {
    stage: "spawn",
    last_method: "",
    child_exit_code: null,
    child_signal: null,
    child_error_code: "",
    child_error_syscall: "",
    stdout_parse_errors: 0,
    stderr_length: 0,
  };
  const evidence = {
    initialize: { ok: false },
    tools_list: { ok: false },
    calls: {
      workspace_list: { ok: false },
      runtime_capabilities: { ok: false },
      runtime_run_test: [],
    },
    diagnostic: diagnostics,
  };
  let child = null;
  let buffer = "";
  let stderr = "";

  const rejectAll = (error) => {
    for (const entry of pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(error);
    }
    pending.clear();
  };

  if (typeof serverPath !== "string" || !fs.existsSync(serverPath)) {
    diagnostics.stage = "spawn";
    return { ok: false, blocker: "mcp_server_spawn_failed", evidence };
  }

  try {
    child = spawn(process.execPath, [serverPath], {
      cwd: workspaceRoot,
      env: {
        ...env,
        VAULT_WORKSPACE_ROOT: workspaceRoot,
        MCP_AUDIT_DIR: auditDir,
        MCP_TRASH_DIR: trashDir,
        MCP_AUTO_APPROVE: "0",
        MCP_FRAMING: "newline",
      },
      stdio: ["pipe", "pipe", "pipe"],
    });

    child.stdin.on("error", (error) => {
      diagnostics.stage = "transport";
      rejectAll(normalizeProbeError(error, "mcp_transport_write_failed"));
    });
    child.stdout.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        let message;
        try {
          message = JSON.parse(line);
        } catch {
          diagnostics.stdout_parse_errors += 1;
          continue;
        }
        if (message.id == null || !pending.has(message.id)) continue;
        const entry = pending.get(message.id);
        pending.delete(message.id);
        clearTimeout(entry.timer);
        entry.resolve(message);
      }
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
      diagnostics.stderr_length = Buffer.byteLength(stderr, "utf8");
    });
    child.on("error", (error) => {
      diagnostics.child_error_code = String(error?.code || "");
      diagnostics.child_error_syscall = String(error?.syscall || "");
      diagnostics.stage = diagnostics.last_method || "spawn";
      rejectAll(normalizeProbeError(error, "mcp_server_spawn_failed"));
    });
    child.on("exit", (code, signal) => {
      diagnostics.child_exit_code = Number.isInteger(code) ? code : null;
      diagnostics.child_signal = signal || null;
      if (pending.size) {
        diagnostics.stage = diagnostics.last_method || "spawn";
        rejectAll(normalizeProbeError(null, "mcp_server_exit"));
      }
    });

    const initialized = await request(
      child,
      pending,
      sequence,
      "initialize",
      {
        protocolVersion: "2024-11-05",
        capabilities: {},
        clientInfo: { name: "rts01-agentic-probe", version: "1.0.0" },
      },
      diagnostics,
    );
    evidence.initialize = {
      ok: initialized.result?.serverInfo?.name === "vault-workspace-mcp",
      protocol_version: String(initialized.result?.protocolVersion || ""),
      server_name: String(initialized.result?.serverInfo?.name || ""),
    };
    if (!evidence.initialize.ok) {
      throw Object.assign(new Error("mcp_initialize_invalid"), { code: "mcp_initialize_invalid" });
    }

    child.stdin.write(JSON.stringify({
      jsonrpc: "2.0",
      method: "notifications/initialized",
      params: {},
    }) + "\n");

    const listed = await request(child, pending, sequence, "tools/list", {}, diagnostics);
    const names = new Set((listed.result?.tools || []).map((tool) => String(tool.name || "")));
    const required = ["workspace_list", "runtime_capabilities", "runtime_run_test"];
    evidence.tools_list = {
      ok: required.every((name) => names.has(name)),
      tool_count: names.size,
      required_tools_present: required.every((name) => names.has(name)),
    };
    if (!evidence.tools_list.ok) {
      throw Object.assign(new Error("mcp_tools_list_invalid"), { code: "mcp_tools_list_invalid" });
    }

    const listedWorkspace = parseToolResult(
      await request(child, pending, sequence, "tools/call", {
        name: "workspace_list",
        arguments: { dir: ".", maxEntries: 200 },
      }, diagnostics),
      "workspace_list",
    );
    evidence.calls.workspace_list = {
      ok: pathEquals(listedWorkspace.workspace_root, workspaceRoot),
      scope_matches: pathEquals(listedWorkspace.workspace_root, workspaceRoot),
      entry_count: Array.isArray(listedWorkspace.entries) ? listedWorkspace.entries.length : 0,
    };
    if (!evidence.calls.workspace_list.ok) {
      throw Object.assign(new Error("mcp_workspace_scope_mismatch"), {
        code: "mcp_workspace_scope_mismatch",
      });
    }

    const capabilities = parseToolResult(
      await request(child, pending, sequence, "tools/call", {
        name: "runtime_capabilities",
        arguments: {},
      }, diagnostics),
      "runtime_capabilities",
    );
    const codex = capabilities.executor_readiness?.codex || {};
    evidence.calls.runtime_capabilities = {
      ok: codex.installed === true && codex.authenticated === true && codex.headless_ready === true,
      codex_installed: codex.installed === true,
      codex_authenticated: codex.authenticated === true,
      codex_headless_ready: codex.headless_ready === true,
    };
    if (!evidence.calls.runtime_capabilities.ok) {
      throw Object.assign(new Error("mcp_codex_not_ready"), { code: "mcp_codex_not_ready" });
    }

    for (const test of tests) {
      const result = parseToolResult(
        await request(child, pending, sequence, "tools/call", {
          name: "runtime_run_test",
          arguments: {
            runner: test.runner,
            projectDir: test.projectDir || ".",
            target: test.target,
            timeoutSec: test.timeoutSec,
          },
        }, diagnostics, Math.max(5000, (test.timeoutSec + 5) * 1000)),
        "runtime_run_test",
      );
      const stdout = String(result.stdout || "");
      const stderr = String(result.stderr || "");
      evidence.calls.runtime_run_test.push({
        runner: String(result.runner || test.runner),
        target: String(result.target || test.target),
        ok: result.ok === true && result.exit_code === 0,
        exit_code: Number.isInteger(result.exit_code) ? result.exit_code : null,
        timed_out: result.timed_out === true,
        duration_ms: Number.isFinite(result.duration_ms) ? result.duration_ms : null,
        error: String(result.error || "").slice(0, 300),
        stdout_length: Buffer.byteLength(stdout, "utf8"),
        stderr_length: Buffer.byteLength(stderr, "utf8"),
        stderr_tail: redactDiagnostic(stderr),
      });
    }
    const boundedOk = evidence.calls.runtime_run_test.length === tests.length && evidence.calls.runtime_run_test.every((test) => test.ok);
    if (!boundedOk) {
      throw Object.assign(new Error("mcp_bounded_validation_failed"), {
        code: "mcp_bounded_validation_failed",
      });
    }
    return { ok: true, evidence };
  } catch (error) {
    return {
      ok: false,
      blocker: error?.code || "mcp_protocol_probe_failed",
      evidence,
    };
  } finally {
    rejectAll(new Error("mcp_probe_closed"));
    if (child) {
      child.stdin.end();
      child.kill();
    }
  }
}

function pathEquals(left, right) {
  return typeof left === "string" &&
    left.replace(/[\\/]+$/, "").toLowerCase() ===
    String(right).replace(/[\\/]+$/, "").toLowerCase();
}

