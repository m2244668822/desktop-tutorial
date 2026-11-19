import { createHash } from "node:crypto";
import { currentTaskEnvelope, topLevelSections } from "./inbox.js";
import { validatePersistedClaimResult } from "./executor_identity.js";
import { commitOnRemoteRef, readCommittedTask, readGitRevision, readTerminalResult } from "./result_readback.js";

// Approved R4 fixture source in the R4 contract at parent commit 7eecd6f6.
export const R4_SOURCE_SNAPSHOT_SHA = "7f7f2faeddf78521402be5e30cf6cf1cec638358565405d4348c992e81c63a4e";
export const REGISTERED_PROJECT_IDS = Object.freeze([
  "desktop-tutorial",
  "automation-fixture",
  "white-studio-thunder-arcade",
  "white-studio-web",
  "white-studio-games",
  "white-studio-palette-creator",
  "white-studio-game-contributor-kit",
  "partner-site-demo",
]);
const REPLAY_MIN_SPAN_MS = 604800000;
const REPLAY_REQUIRED_RUNS = 3;
const REPLAY_FIELDS = ["task_id", "run_id", "operation_id"];

export const isGitSha = (value) => typeof value === "string" && /^[0-9a-f]{40}(?:[0-9a-f]{24})?$/.test(value);
export const sha256 = (value) => createHash("sha256").update(value).digest("hex");
export const isRunNumber = (value) => typeof value === "string" && /^[1-9]\d*$/.test(value);

export function checkReplayJournal(rows, verifyObservation, now) {
  if (!Array.isArray(rows)) return { reasons: ["missing_replay_journal"], observation_count: 0, span_ms: null, result_span_ms: null };

  const reasons = new Set();
  const identities = Object.fromEntries(REPLAY_FIELDS.map((field) => [field, new Set()]));
  const times = [];
  const resultTimes = [];
  for (const row of rows) {
    if (!row || !REPLAY_FIELDS.every((field) => typeof row[field] === "string" && row[field].trim() === row[field] && row[field])) {
      reasons.add("replay_observation_identity_invalid");
      continue;
    }
    const time = Date.parse(row.observed_at);
    if (Number.isFinite(time) && time <= now) times.push(time);
    else reasons.add("replay_observation_time_invalid");
    if (row.source_snapshot_sha !== R4_SOURCE_SNAPSHOT_SHA) reasons.add("replay_source_snapshot_mismatch");
    for (const field of REPLAY_FIELDS) {
      if (identities[field].has(row[field])) reasons.add("replay_identity_duplicate");
      identities[field].add(row[field]);
    }
    if (row.status !== "done" || row.e1_e5 !== "pass" || row.remote_readback !== "pass" || !isGitSha(row.result_commit)) {
      reasons.add("replay_observation_not_verified");
    } else {
      try {
        const completedAt = verifyObservation(row);
        if (!Number.isFinite(completedAt) || completedAt > time) throw new Error("replay_result_time_invalid");
        resultTimes.push(completedAt);
      } catch {
        reasons.add("replay_result_readback_unverified");
      }
    }
  }

  times.sort((a, b) => a - b);
  resultTimes.sort((a, b) => a - b);
  const span = times.length ? times.at(-1) - times[0] : null;
  const resultSpan = resultTimes.length ? resultTimes.at(-1) - resultTimes[0] : null;
  if (rows.length < REPLAY_REQUIRED_RUNS) reasons.add("replay_observation_count_below_threshold");
  else if (span === null || span < REPLAY_MIN_SPAN_MS) reasons.add("replay_observation_span_below_threshold");
  if (resultTimes.length >= REPLAY_REQUIRED_RUNS && resultSpan < REPLAY_MIN_SPAN_MS) {
    reasons.add("replay_result_span_below_threshold");
  }
  return { reasons: [...reasons], observation_count: rows.length, span_ms: span, result_span_ms: resultSpan };
}

export function verifyReplayResult(row, repoRoot) {
  if (!/^rts01-high-automation-evidence-20261107-r4(?:-observation-[A-Za-z0-9._-]+)?$/.test(row.task_id)) {
    throw new Error("replay_task_outside_r4");
  }
  const taskPath = "智能體/tasks/" + row.task_id + ".md";
  if (!commitOnRemoteRef(repoRoot, row.result_commit, [
    "refs/remotes/origin/main",
    "refs/remotes/origin/codex/rts01-task-review-20261106",
  ])) throw new Error("replay_result_remote_ref_missing");
  const text = readCommittedTask(row.result_commit, taskPath, repoRoot);
  const result = readTerminalResult(text, row.task_id, "replay");
  const identity = validatePersistedClaimResult(text, row.task_id);
  const claim = topLevelSections(text).find(({ heading }) => heading === "## Executor Claim")?.text ?? "";
  const operation = claim.match(/^- operation_id[:：][ \t]*\x60([^\x60\r\n]+)\x60/m)?.[1];
  const source = currentTaskEnvelope(text).match(/^source_snapshot_sha[ \t]+([0-9a-f]+)[ \t]*\r?$/m)?.[1];
  const revision = result.fields.get("remote_task_revision");
  const completedAt = Date.parse(result.fields.get("completed_at"));

  if (result.status !== "done" || !identity.ok || identity.legacy ||
      result.fields.get("run_id") !== row.run_id || operation !== row.operation_id ||
      source !== row.source_snapshot_sha || !isGitSha(revision) ||
      readGitRevision(repoRoot, row.result_commit + "^:" + taskPath) !== revision ||
      !Number.isFinite(completedAt)) {
    throw new Error("replay_result_identity_mismatch");
  }
  return completedAt;
}

export function checkRegisteredProjects(packet, profiles, context, now) {
  if (!packet) return { reasons: ["missing_registered_projects_evidence"], project_count: 0 };

  const reasons = new Set();
  const records = Array.isArray(packet.registered_projects) ? packet.registered_projects : [];
  const time = Date.parse(packet.generated_at);
  if (packet.schema_version !== 1 || packet.kind !== "registered_projects_evidence" ||
      packet.source_snapshot_sha !== R4_SOURCE_SNAPSHOT_SHA || !Number.isFinite(time) || time > now ||
      packet.status !== "pass" || packet.arbitrary_commands !== false || packet.writes_forbidden !== true) {
    reasons.add("registered_projects_packet_not_passed");
  }
  const origin = packet.provenance;
  if (!context || !origin || origin.runner_environment !== "self-hosted" ||
      origin.repository !== context.repository || origin.ref !== context.ref ||
      origin.workspace_sha !== context.workspace_sha || origin.runtime_sha !== context.runtime_sha ||
      !isRunNumber(origin.run_id) || !isRunNumber(origin.run_attempt)) {
    reasons.add("registered_projects_provenance_mismatch");
  }

  const ids = records.map((record) => record?.project_id);
  if (ids.length !== REGISTERED_PROJECT_IDS.length || !REGISTERED_PROJECT_IDS.every((id) => ids.includes(id))) {
    reasons.add("registered_project_set_incomplete");
  }
  for (const id of REGISTERED_PROJECT_IDS) {
    const profile = profiles?.projects?.[id];
    const record = records.find((item) => item?.project_id === id);
    if (!profile || profile.automation_mode !== "bounded_write" || !record ||
        record.root !== profile.root || record.profile_sha256 !== sha256(JSON.stringify(profile))) {
      reasons.add("registered_project_profile_mismatch:" + id);
      continue;
    }
    const fixed = profile.tests;
    const actual = record.fixed_tests;
    if (record.status !== "pass" || record.root_exists !== true ||
        !Array.isArray(fixed) || !fixed.length || !Array.isArray(actual) || actual.length !== fixed.length ||
        !fixed.every((test, index) => {
          const result = actual[index];
          return test && result && result.runner === test.runner && result.target === test.target &&
            result.timeout_sec === test.timeoutSec && Number.isInteger(test.timeoutSec) &&
            test.timeoutSec >= 1 && test.timeoutSec <= 120 &&
            result.status === "pass" && result.ok === true && result.timed_out === false && result.exit_code === 0;
        })) {
      reasons.add("registered_project_fixed_test_mismatch:" + id);
    }
  }
  return { reasons: [...reasons], project_count: records.length };
}
