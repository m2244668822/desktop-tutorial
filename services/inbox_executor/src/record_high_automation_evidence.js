#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import {
  validateLongTermReplayEvidence,
  validateRegisteredProjectsEvidence,
} from "./evidence_schema.js";
import { REGISTERED_PROJECT_IDS } from "./registered_projects_evidence.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const runtimeRoot = path.resolve(here, "..", "..", "..", "..");
const repoRoot = path.resolve(runtimeRoot, "..");

function argument(name, fallback = "") {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function pass(value) {
  return value ? "pass" : "fail";
}

function textBetween(source, start, end) {
  const startIndex = source.indexOf(start);
  if (startIndex < 0) return "";
  const body = source.slice(startIndex + start.length);
  const endIndex = end ? body.indexOf(end) : -1;
  return (endIndex >= 0 ? body.slice(0, endIndex) : body).trim();
}

function markdownValue(source, label) {
  for (const line of source.split(/\r?\n/)) {
    const match = line.match(/^[-*]\s*(.*?)\s*[:：]\s*(.*?)\s*$/);
    if (match && match[1].replace(/`/g, "").trim() === label) {
      return match[2].replace(/`/g, "").trim();
    }
  }
  return "";
}

export function resultEvidence(taskText) {
  const actions = ["workspace.create", "workspace.patch", "workspace.move", "workspace.trash"];
  const result = {
    task_id: markdownValue(taskText, "task_id"),
    run_id: markdownValue(taskText, "run_id"),
    lease_id: markdownValue(taskText, "lease_id"),
    lease_generation: markdownValue(taskText, "lease_generation"),
    fencing_token: markdownValue(taskText, "fencing_token"),
    remote_task_revision: markdownValue(taskText, "remote_task_revision"),
    status: markdownValue(taskText, "結果"),
    identity_validation: markdownValue(taskText, "identity_validation"),
    action_results: Object.fromEntries(actions.map((action) => [action, taskText.includes(`\`${action}\` ok`)])),
  };
  result.all_actions_ok = actions.every((action) => result.action_results[action]);
  result.claim_identity_complete = [result.task_id, result.run_id, result.lease_id, result.lease_generation, result.fencing_token, result.remote_task_revision].every(Boolean);
  return result;
}

export function casResultWritebackPass(result) {
  return ["done", "blocked"].includes(result.status) && result.claim_identity_complete;
}

export function buildHighAutomationEvidence({
  phase,
  taskText,
  r3,
  profiles = {
    projects: {
      "obsidian-vault-refactor-2026-09-08": {
        automation_mode: "manual_only",
        allowed_write_tools: [],
      },
    },
  },
  registeredProjects,
  longTermReplay,
  sourceSnapshotSha,
  repoRoot: evidenceRepoRoot = repoRoot,
  phasePath = "",
  taskPath = "",
  r3Path = "",
} = {}) {
  if (!registeredProjects) throw new Error("registered_projects_packet_missing");
  if (!longTermReplay) throw new Error("long_term_replay_packet_missing");
  if (!sourceSnapshotSha) throw new Error("source_snapshot_sha_missing");
  validateRegisteredProjectsEvidence(registeredProjects, { expectedProjectIds: REGISTERED_PROJECT_IDS });
  validateLongTermReplayEvidence(longTermReplay, { expectedSourceSnapshotSha: sourceSnapshotSha });

  const primary = profiles.projects?.["obsidian-vault-refactor-2026-09-08"] || {};
  const result = resultEvidence(taskText);
  const phaseRows = Array.isArray(phase.phases)
    ? phase.phases
    : Object.entries(phase.phases || {}).map(([name, item]) => ({ name, ...item }));
  const phasePass = Object.fromEntries(["A", "B", "C", "D", "E"].map((name) => [name, phaseRows.find((item) => item.name === name)?.status === "pass"]));
  const r3Pass = r3.status === "VERIFIED_BASELINE" &&
    r3.verification?.hard_gates === "PASS" &&
    r3.verification?.evidence_packet_recovery === "PASS" &&
    r3.verification?.durable_task_result === "PASS" &&
    r3.verification?.primary_vault_modified === false;

  return {
    schema_version: "1.0.0",
    kind: "mcp_high_automation_evidence",
    generated_at: new Date().toISOString(),
    workflow_run_id: process.env.GITHUB_RUN_ID || "local",
    workflow_sha: process.env.GITHUB_SHA || "unknown",
    source_snapshot_sha: sourceSnapshotSha,
    phases: Object.fromEntries(Object.entries(phasePass).map(([name, ok]) => [name, { status: pass(ok) }])),
    gates: {
      lease_fencing: pass(result.claim_identity_complete && result.identity_validation === "executor_identity_match"),
      state_hash: pass(phasePass.B),
      append_only_journal: pass(phasePass.A),
      cas_result_writeback: pass(casResultWritebackPass(result)),
      primary_protection: pass(primary.automation_mode === "manual_only" && Array.isArray(primary.allowed_write_tools) && primary.allowed_write_tools.length === 0),
      r3_baseline: pass(r3Pass),
    },
    registered_projects: registeredProjects,
    long_term_replay: longTermReplay,
    task_result: {
      source_path: taskPath ? path.relative(evidenceRepoRoot, taskPath).replace(/\\/g, "/") : "",
      ...(taskPath ? { sha256: sha256(taskPath) } : {}),
      ...result,
    },
    phase_evidence: {
      source_path: phasePath ? path.relative(evidenceRepoRoot, phasePath).replace(/\\/g, "/") : "",
      ...(phasePath ? { sha256: sha256(phasePath) } : {}),
      overall: phase.overall,
      scope: phase.scope,
    },
    r3_baseline: {
      source_path: r3Path ? path.relative(evidenceRepoRoot, r3Path).replace(/\\/g, "/") : "",
      ...(r3Path ? { sha256: sha256(r3Path) } : {}),
      release_candidate: r3.release_candidate,
      status: r3.status,
      parent_release_commit: r3.parent_release_commit,
      runtime_commit: r3.runtime_child?.commit,
    },
    primary_policy: {
      project_id: "obsidian-vault-refactor-2026-09-08",
      automation_mode: primary.automation_mode,
      allowed_write_tools: primary.allowed_write_tools,
    },
  };
}

function main() {
  const phaseArg = argument("--phase");
  const taskArg = argument("--task");
  const r3Arg = argument("--r3");
  const registeredArg = argument("--registered-projects");
  const replayArg = argument("--long-term-replay");
  const sourceSnapshotArg = argument("--source-snapshot-sha");
  if (!phaseArg || !taskArg || !r3Arg || !registeredArg || !replayArg || !sourceSnapshotArg) throw new Error("Usage: --phase <json> --task <markdown> --r3 <json> --registered-projects <json> --long-term-replay <json> --source-snapshot-sha <sha> [--output <json>]");
  const phasePath = path.resolve(phaseArg);
  const taskPath = path.resolve(taskArg);
  const r3Path = path.resolve(r3Arg);
  const registeredPath = path.resolve(registeredArg);
  const replayPath = path.resolve(replayArg);
  const outputPath = path.resolve(argument("--output", path.join(repoRoot, "runtime", ".mcp-state", "high-automation-evidence.json")));

  const phase = readJson(phasePath);
  const taskText = fs.readFileSync(taskPath, "utf8");
  const r3 = readJson(r3Path);
  const profiles = readJson(path.join(repoRoot, "runtime", "test-profiles.json"));
  const registeredProjects = readJson(registeredPath);
  const longTermReplay = readJson(replayPath);
  const evidence = buildHighAutomationEvidence({
    phase,
    taskText,
    r3,
    profiles,
    registeredProjects,
    longTermReplay,
    sourceSnapshotSha: sourceSnapshotArg,
    phasePath,
    taskPath,
    r3Path,
  });
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(evidence, null, 2) + "\n", "utf8");
  console.log(JSON.stringify({ output: outputPath, gates: evidence.gates }, null, 2));
  if (Object.values(evidence.gates).some((value) => value !== "pass")) process.exitCode = 1;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  main();
}
