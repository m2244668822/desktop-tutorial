import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import {
  R4_SOURCE_SNAPSHOT_SHA, checkRegisteredProjects, checkReplayJournal,
  isGitSha, isRunNumber, sha256, verifyReplayResult,
} from "./r4_evidence.js";
import { commitOnRemoteRef, readCommittedTask, readGitRevision, verifyResultReadback } from "./result_readback.js";
import { validatePersistedClaimResult } from "./executor_identity.js";

const RECORD_KIND = "mcp_high_automation_evidence";
const PHASES = ["A", "B", "C", "D", "E"];
const RUN_KEYS = ["workspace_sha", "runtime_sha", "run_id", "run_attempt"];
const RUNNER_KEYS = [...RUN_KEYS, "repository", "ref", "runner_environment"];

export function runnerContext(env = process.env) {
  const context = {
    workspace_sha: env.GITHUB_SHA,
    runtime_sha: env.WHITE_STUDIO_RUNTIME_SHA,
    run_id: env.GITHUB_RUN_ID,
    run_attempt: env.GITHUB_RUN_ATTEMPT,
    repository: env.GITHUB_REPOSITORY,
    ref: env.GITHUB_REF,
    runner_environment: env.RUNNER_ENVIRONMENT,
  };
  if (env.GITHUB_ACTIONS !== "true" || !runnerProvenance(context)) return null;
  return context;
}

function runnerProvenance(context) {
  return context && typeof context.ref === "string" && context.ref.startsWith("refs/heads/") &&
    context.runner_environment === "self-hosted" &&
    /^[\w.-]+\/[\w.-]+$/.test(context.repository) &&
    isGitSha(context.workspace_sha) && isGitSha(context.runtime_sha) &&
    isRunNumber(context.run_id) && isRunNumber(context.run_attempt);
}

function sameProvenance(expected, actual, keys) {
  return Boolean(expected && actual && keys.every((key) => actual[key] === expected[key]));
}

function verdict(reasons) {
  const ready = reasons.length === 0;
  return { ready, status: ready ? "MCP_HIGH_AUTOMATION_READY" : "MCP_HIGH_AUTOMATION_NOT_READY", reasons };
}

export function assessHighAutomation({
  context, phase, r3, profiles, replayJournal, registeredProjects, readback,
  verifyObservation, verifyCas, inputReasons = [], now = Date.now(),
} = {}) {
  const reasons = new Set(inputReasons);
  if (!runnerProvenance(context)) reasons.add("formal_runner_context_missing");
  else if (context.ref !== "refs/heads/main") reasons.add("validation_ref_not_main");

  if (!phase) reasons.add("missing_phase_evidence");
  else {
    if (phase.schema_version !== "1.0.0" || phase.kind !== "windows_phase_a_e_acceptance" ||
        phase.overall !== "PASS" || !Array.isArray(phase.phases) ||
        phase.phases.length !== PHASES.length ||
        !PHASES.every((name) => phase.phases.some((entry) => entry?.name === name && entry.status === "pass"))) {
      reasons.add("phase_acceptance_not_passed");
    }
    if (!sameProvenance(context, phase.provenance, RUN_KEYS)) reasons.add("phase_provenance_mismatch");
  }
  if (!r3) reasons.add("missing_r3_evidence");
  else if (r3.release_candidate !== "R3" || r3.status !== "VERIFIED_BASELINE" ||
      r3.verification?.hard_gates !== "PASS" || r3.verification.evidence_packet_recovery !== "PASS" ||
      r3.verification.durable_task_result !== "PASS" || r3.verification.primary_vault_modified !== false) {
    reasons.add("r3_baseline_not_passed");
  }
  const primary = profiles?.projects?.["obsidian-vault-refactor-2026-09-08"];
  if (!profiles) reasons.add("missing_test_profiles");
  else if (profiles.policy?.arbitrary_shell !== false || profiles.policy.unknown_project !== "blocked" ||
      primary?.automation_mode !== "manual_only" || !Array.isArray(primary.allowed_write_tools) ||
      primary.allowed_write_tools.length !== 0) {
    reasons.add("primary_protection_not_passed");
  }

  const replay = checkReplayJournal(replayJournal, verifyObservation, now);
  const projects = checkRegisteredProjects(registeredProjects, profiles, context, now);
  for (const reason of [...replay.reasons, ...projects.reasons]) reasons.add(reason);

  let cas = null;
  if (!readback) reasons.add("missing_cas_readback_evidence");
  else if (!sameProvenance(context, readback.provenance, RUNNER_KEYS)) {
    reasons.add("cas_readback_provenance_mismatch");
  } else {
    try {
      cas = verifyCas(readback);
      if (!cas?.task_id || !cas?.trace_id) throw new Error("cas_readback_result_incomplete");
    } catch (error) {
      reasons.add("cas_readback_unverified");
      if (error.code) reasons.add(error.code);
    }
  }

  return {
    ...verdict([...reasons]),
    provenance: context ?? null,
    source_snapshot_sha: R4_SOURCE_SNAPSHOT_SHA,
    replay: { observation_count: replay.observation_count, span_ms: replay.span_ms, result_span_ms: replay.result_span_ms },
    registered_projects: { project_count: projects.project_count },
    cas,
  };
}

export function verifyCasReadback(proof, context, repoRoot) {
  const { task_path: taskPath, task_id: taskId, local_result_commit: local, remote_result_commit: remote } = proof;
  if (proof.schema_version !== 1 || proof.kind !== "rts01_cas_readback" ||
      !/^(?:智能體\/tasks\/[A-Za-z0-9._-]+\.md|智能體\/chatgpt-inbox\.md)$/.test(taskPath) ||
      !taskId || !isGitSha(local) || !isGitSha(remote) || !isGitSha(proof.queued_task_revision) ||
      proof.target_branch !== "main") {
    throw new Error("cas_readback_shape_invalid");
  }
  if (readGitRevision(repoRoot, local + "^") !== context.workspace_sha ||
      readGitRevision(repoRoot, local + "^:" + taskPath) !== proof.queued_task_revision ||
      readGitRevision(repoRoot, context.workspace_sha + ":runtime/desktop-tutorial") !== context.runtime_sha ||
      !commitOnRemoteRef(repoRoot, remote, ["refs/remotes/origin/main"])) {
    throw new Error("cas_readback_checkout_or_revision_mismatch");
  }
  const localText = readCommittedTask(local, taskPath, repoRoot);
  const remoteText = readCommittedTask(remote, taskPath, repoRoot);
  const result = verifyResultReadback(localText, remoteText, taskId);
  const identity = validatePersistedClaimResult(remoteText, taskId);
  if (result.status !== "done" || result.trace_id !== proof.trace_id || !identity.ok || identity.legacy) {
    throw new Error("cas_readback_identity_or_trace_mismatch");
  }
  return { ...result, queued_task_revision: proof.queued_task_revision, local_result_commit: local, remote_result_commit: remote };
}

function decodeJournal(text) {
  return text.split(/\r?\n/).filter((line) => line.trim()).map((line) => JSON.parse(line));
}

export function loadEvidenceInputs(args = process.argv.slice(2), env = process.env) {
  const optionNames = ["phase", "r3", "profiles", "journal", "registered-projects", "readback", "output"];
  const { values } = parseArgs({
    args,
    options: Object.fromEntries(optionNames.map((name) => [name, { type: "string" }])),
  });
  if (!values.output) throw new Error("high_automation_output_path_required");

  const repoRoot = path.resolve(env.VAULT_WORKSPACE_ROOT || fileURLToPath(new URL("../../../../../", import.meta.url)));
  const state = path.join(repoRoot, "runtime", ".mcp-state");
  const context = runnerContext(env);
  const inputHashes = {};
  const inputReasons = [];
  const outputPath = path.resolve(values.output);
  const read = (name, file, decode = JSON.parse) => {
    inputHashes[name] = null;
    if (!file) return null;
    if (path.resolve(file) === outputPath) throw new Error("high_automation_output_overlaps_input");
    try {
      const bytes = fs.readFileSync(file);
      inputHashes[name] = sha256(bytes);
      return decode(bytes.toString("utf8").replace(/^\uFEFF/, ""));
    } catch (error) {
      if (error.code !== "ENOENT") inputReasons.push("invalid_" + name);
      return null;
    }
  };
  const inputs = {
    context, inputReasons, inputHashes,
    phase: read("phase_evidence", values.phase),
    r3: read("r3_evidence", values.r3 || path.join(repoRoot, "runtime", "database-structural-baseline-release-candidate.json")),
    profiles: read("test_profiles", values.profiles || path.join(repoRoot, "runtime", "test-profiles.json")),
    replayJournal: read("replay_journal", values.journal || path.join(state, "long-term-replay.jsonl"), decodeJournal),
    registeredProjects: read("registered_projects_evidence", values["registered-projects"] || path.join(state, "registered-projects-evidence.json")),
    readback: read("cas_readback_evidence", values.readback),
    verifyObservation: (row) => verifyReplayResult(row, repoRoot),
    verifyCas: (proof) => verifyCasReadback(proof, context, repoRoot),
  };
  if (context) {
    for (const [data, source, reason] of [
      [inputs.r3, "runtime/database-structural-baseline-release-candidate.json", "r3_baseline_checkout_mismatch"],
      [inputs.profiles, "runtime/test-profiles.json", "test_profiles_checkout_mismatch"],
    ]) {
      if (!data) continue;
      try {
        const pinned = JSON.parse(readCommittedTask(context.workspace_sha, source, repoRoot));
        if (JSON.stringify(data) !== JSON.stringify(pinned)) inputReasons.push(reason);
      } catch {
        inputReasons.push(reason);
      }
    }
  }
  return { inputs, outputPath };
}

export function recordEvidence(inputs, outputPath) {
  const record = {
    schema_version: 1,
    kind: RECORD_KIND,
    generated_at: new Date().toISOString(),
    input_hashes: inputs.inputHashes,
    assessment: assessHighAutomation(inputs),
  };
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(record, null, 2) + "\n", { encoding: "utf8", flag: "wx" });
  return record;
}

export function verifyRecordedEvidence(record, inputs) {
  const assessment = assessHighAutomation(inputs);
  const reasons = [...assessment.reasons];
  if (record?.schema_version !== 1 || record.kind !== RECORD_KIND) {
    reasons.push("missing_or_invalid_recorder_report");
  } else {
    if (JSON.stringify(record.input_hashes) !== JSON.stringify(inputs.inputHashes)) {
      reasons.push("recorded_input_digest_mismatch");
    }
    if (JSON.stringify(record.assessment) !== JSON.stringify(assessment)) {
      reasons.push("recorded_assessment_mismatch");
    }
  }
  return { ...assessment, ...verdict(reasons) };
}
