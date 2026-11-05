#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vaultRoot = path.resolve(
  process.env.VAULT_WORKSPACE_ROOT || path.join(__dirname, "..", "..", "..", "..")
);
const queueCli = path.join(__dirname, "queue_cli.js");
const daemon = path.join(__dirname, "daemon.js");
const agentic = path.join(__dirname, "agentic_executor.js");
const once = process.argv.includes("--once");
const pollMs = Math.max(1000, Math.min(Number(process.env.WHITE_STUDIO_LOCAL_POLL_MS || 3000), 60000));

function runNode(script, args = [], env = process.env) {
  return spawnSync(process.execPath, [script, ...args], {
    cwd: vaultRoot,
    encoding: "utf8",
    env,
    maxBuffer: 8 * 1024 * 1024,
  });
}

function selectQueued() {
  const outputPath = path.join(os.tmpdir(), `white-studio-local-queue-${process.pid}.txt`);
  fs.writeFileSync(outputPath, "", "utf8");
  const run = runNode(queueCli, [], {
    ...process.env,
    VAULT_WORKSPACE_ROOT: vaultRoot,
    GITHUB_OUTPUT: outputPath,
  });
  const lines = fs.readFileSync(outputPath, "utf8").split(/\r?\n/).filter(Boolean);
  try { fs.unlinkSync(outputPath); } catch {}
  if (run.status !== 0) {
    return { ok: false, code: "queue_cli_failed", stderr: String(run.stderr || "").trim() };
  }
  const fields = Object.fromEntries(lines.map((line) => {
    const at = line.indexOf("=");
    return [line.slice(0, at), line.slice(at + 1)];
  }));
  if (fields.ok !== "true") {
    return { ok: false, code: fields.code || "queue_empty" };
  }
  return {
    ok: true,
    task_id: fields.task_id,
    route: fields.route,
    task_path: Buffer.from(fields.task_path_b64, "base64").toString("utf8"),
  };
}

function executeOne(selection) {
  const taskPath = path.resolve(vaultRoot, selection.task_path);
  const rel = path.relative(vaultRoot, taskPath);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    return { ok: false, code: "task_outside_vault" };
  }
  const script = selection.route === "mechanical" ? daemon : agentic;
  const env = {
    ...process.env,
    VAULT_WORKSPACE_ROOT: vaultRoot,
    INBOX_PATH: taskPath,
  };
  const run = runNode(script, selection.route === "mechanical" ? ["--once"] : [], env);
  return {
    ok: run.status === 0,
    task_id: selection.task_id,
    route: selection.route,
    exit_code: run.status,
    stdout: String(run.stdout || "").slice(-4000),
    stderr: String(run.stderr || "").slice(-4000),
  };
}

function tick() {
  const selected = selectQueued();
  if (!selected.ok) {
    if (selected.code !== "queue_empty") {
      process.stderr.write(`[local-queue] ${new Date().toISOString()} ${selected.code}\n`);
    }
    return false;
  }
  process.stderr.write(
    `[local-queue] ${new Date().toISOString()} selected task_id=${selected.task_id} route=${selected.route}\n`
  );
  const result = executeOne(selected);
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  return true;
}

process.stderr.write(
  `[local-queue] vault=${vaultRoot} poll_ms=${pollMs} once=${once}\n`
);
tick();
if (!once) setInterval(tick, pollMs);
