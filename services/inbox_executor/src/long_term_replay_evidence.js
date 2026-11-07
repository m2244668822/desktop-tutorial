#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  assertJsonSchema,
  readJsonSchema,
  REPLAY_MIN_SPAN_MS,
} from "./evidence_schema.js";

export const REPLAY_REQUIRED_RUNS = 3;
export { REPLAY_MIN_SPAN_MS };

function fail(code, details = "") {
  const error = new Error(details ? `${code}: ${details}` : code);
  error.code = code;
  throw error;
}

function readRows(journalPath) {
  if (!fs.existsSync(journalPath)) return [];
  const text = fs.readFileSync(journalPath, "utf8");
  return text
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line);
      } catch {
        fail("replay_journal_invalid_json", `line=${index + 1}`);
      }
    });
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function assertObservation(observation, expectedSourceSnapshotSha = "") {
  if (!observation || typeof observation !== "object" || Array.isArray(observation)) fail("replay_observation_invalid");
  for (const field of ["task_id", "run_id", "operation_id", "observed_at", "source_snapshot_sha", "result_commit"]) {
    if (typeof observation[field] !== "string" || !observation[field].trim()) fail(`replay_${field}_missing`);
  }
  if (Number.isNaN(Date.parse(observation.observed_at))) fail("replay_observed_at_invalid");
  if (expectedSourceSnapshotSha && observation.source_snapshot_sha !== expectedSourceSnapshotSha) fail("replay_source_snapshot_mismatch");
  if (observation.status !== "done") fail("replay_observation_not_done");
  if (observation.e1_e5 !== "pass") fail("replay_e1_e5_not_passed");
  if (observation.remote_readback !== "pass") fail("replay_remote_readback_not_passed");
}

function identityCheck(observations) {
  const seen = new Map([
    ["task_id", new Set()],
    ["run_id", new Set()],
    ["operation_id", new Set()],
  ]);
  for (const observation of observations) {
    for (const [field, values] of seen) {
      if (values.has(observation[field])) fail("replay_identity_duplicate", field);
      values.add(observation[field]);
    }
  }
}

function sanitizedObservation(observation) {
  return {
    task_id: observation.task_id,
    run_id: observation.run_id,
    operation_id: observation.operation_id,
    observed_at: observation.observed_at,
    source_snapshot_sha: observation.source_snapshot_sha,
    status: observation.status,
    e1_e5: observation.e1_e5,
    result_commit: observation.result_commit,
    remote_readback: observation.remote_readback,
  };
}

function packet({ journalPath, observations, expectedSourceSnapshotSha, requiredRuns, minSpanMs }) {
  identityCheck(observations);
  const source = expectedSourceSnapshotSha || observations[0]?.source_snapshot_sha || "";
  if (!source) fail("replay_source_snapshot_missing");
  for (const observation of observations) assertObservation(observation, source);
  const ordered = [...observations].sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at));
  const reasons = [];
  if (ordered.length < requiredRuns) reasons.push("replay_observation_count_below_threshold");
  if (ordered.length >= requiredRuns) {
    const span = Date.parse(ordered.at(-1).observed_at) - Date.parse(ordered[0].observed_at);
    if (span < minSpanMs) reasons.push("replay_observation_span_below_threshold");
  }
  const result = {
    schema_version: 1,
    kind: "long_term_replay_evidence",
    generated_at: new Date().toISOString(),
    source_snapshot_sha: source,
    required_runs: requiredRuns,
    min_span_ms: minSpanMs,
    observations: ordered.map(sanitizedObservation),
    status: reasons.length === 0 ? "pass" : "not_ready",
    reasons,
    append_only: true,
    journal_path: path.resolve(journalPath),
  };
  return result;
}

export function evaluateReplayEvidence({
  journalPath,
  expectedSourceSnapshotSha = "",
  requiredRuns = REPLAY_REQUIRED_RUNS,
  minSpanMs = REPLAY_MIN_SPAN_MS,
  schemaPath = "",
} = {}) {
  const observations = readRows(journalPath);
  const result = packet({ journalPath, observations, expectedSourceSnapshotSha, requiredRuns, minSpanMs });
  if (schemaPath && fs.existsSync(schemaPath)) assertJsonSchema(result, readJsonSchema(schemaPath), "long_term_replay");
  return result;
}

export function appendReplayObservation({
  journalPath,
  observation,
  expectedSourceSnapshotSha = "",
  requiredRuns = REPLAY_REQUIRED_RUNS,
  minSpanMs = REPLAY_MIN_SPAN_MS,
  schemaPath = "",
} = {}) {
  const existing = readRows(journalPath);
  const source = expectedSourceSnapshotSha || existing[0]?.source_snapshot_sha || observation?.source_snapshot_sha || "";
  assertObservation(observation, source);
  identityCheck([...existing, observation]);
  const clean = sanitizedObservation(observation);
  fs.mkdirSync(path.dirname(journalPath), { recursive: true });
  // Append exactly one sanitized JSON object. Prior lines are never rewritten.
  fs.appendFileSync(journalPath, JSON.stringify(clean) + "\n", "utf8");
  return evaluateReplayEvidence({ journalPath, expectedSourceSnapshotSha: source, requiredRuns, minSpanMs, schemaPath });
}

function markdownValue(source, label) {
  for (const line of source.split(/\r?\n/)) {
    const match = line.match(/^[-*]\s*(.*?)\s*[:：]\s*(.*?)\s*$/);
    if (match && match[1].replace(/`/g, "").trim() === label) return match[2].replace(/`/g, "").trim();
  }
  return "";
}

export function observationFromTask({ taskPath, sourceSnapshotSha, resultCommit, observedAt = new Date().toISOString() }) {
  const text = fs.readFileSync(taskPath, "utf8");
  const status = markdownValue(text, "結果");
  const identity = markdownValue(text, "identity_validation");
  const taskId = markdownValue(text, "task_id");
  const source = sourceSnapshotSha || markdownValue(text, "source_snapshot_sha");
  if (!taskId || !source) fail("replay_task_identity_missing");
  return {
    task_id: taskId,
    run_id: markdownValue(text, "run_id"),
    operation_id: markdownValue(text, "operation_id"),
    observed_at: observedAt,
    source_snapshot_sha: source,
    status,
    e1_e5: identity === "executor_identity_match" && text.includes("E5") ? "pass" : "fail",
    result_commit: resultCommit,
    remote_readback: text.includes("remote readback") || text.includes("遠端 readback") || text.includes("E5") ? "pass" : "fail",
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const arg = (name, fallback = "") => {
    const index = process.argv.indexOf(name);
    return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
  };
  const repoRoot = path.resolve(process.env.VAULT_WORKSPACE_ROOT || path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", ".."));
  const journalPath = path.resolve(arg("--journal", path.join(repoRoot, "runtime", ".mcp-state", "long-term-replay.jsonl")));
  const outputPath = path.resolve(arg("--output", path.join(repoRoot, "runtime", ".mcp-state", "long-term-replay-evidence.json")));
  const schemaPath = path.join(repoRoot, "runtime", ".mcp-state", "long-term-replay-evidence.schema.json");
  const taskPath = arg("--task");
  const sourceSnapshotSha = arg("--source-snapshot-sha", process.env.RTS01_SOURCE_SNAPSHOT_SHA || "");
  const taskId = taskPath ? markdownValue(fs.readFileSync(taskPath, "utf8"), "task_id") : "";
  let result;
  if (taskId.startsWith("rts01-high-automation-evidence-20261107-r4")) {
    const observation = observationFromTask({
      taskPath,
      sourceSnapshotSha,
      resultCommit: arg("--result-commit", process.env.GITHUB_SHA || "unknown"),
      observedAt: arg("--observed-at", new Date().toISOString()),
    });
    result = appendReplayObservation({ journalPath, observation, expectedSourceSnapshotSha: sourceSnapshotSha, schemaPath });
  } else {
    result = evaluateReplayEvidence({ journalPath, expectedSourceSnapshotSha: sourceSnapshotSha, schemaPath });
  }
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify({ ...result, journal_sha256: fs.existsSync(journalPath) ? sha256File(journalPath) : "" }, null, 2) + "\n", "utf8");
  process.stdout.write(JSON.stringify({ output: outputPath, status: result.status, reasons: result.reasons, observations: result.observations.length }, null, 2) + "\n");
  if (result.status === "fail") process.exitCode = 1;
}
