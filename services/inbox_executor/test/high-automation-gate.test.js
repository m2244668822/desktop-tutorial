import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { assessHighAutomation, runnerContext, verifyRecordedEvidence } from "../src/high_automation_evidence.js";
import { checkRegisteredProjects, REGISTERED_PROJECT_IDS, R4_SOURCE_SNAPSHOT_SHA, sha256 } from "../src/r4_evidence.js";
import { collectRegisteredProjectsEvidence } from "../src/registered_projects_evidence.js";

const now = Date.parse("2026-11-19T03:00:00Z");
const context = {
  repository: "owner/test-vault",
  ref: "refs/heads/main",
  runner_environment: "self-hosted",
  workspace_sha: "a".repeat(40),
  runtime_sha: "b".repeat(40),
  run_id: "123",
  run_attempt: "2",
};

function fixture() {
  const profiles = {
    policy: { arbitrary_shell: false, unknown_project: "blocked" },
    projects: {
      "obsidian-vault-refactor-2026-09-08": { automation_mode: "manual_only", allowed_write_tools: [] },
      ...Object.fromEntries(REGISTERED_PROJECT_IDS.map((id) => [id, {
        root: "projects/" + id,
        automation_mode: "bounded_write",
        tests: [{ runner: "static_smoke", target: "index.html", timeoutSec: 30 }],
      }])),
    },
  };
  return {
    context,
    now,
    phase: {
      schema_version: "1.0.0",
      kind: "windows_phase_a_e_acceptance",
      overall: "PASS",
      provenance: context,
      phases: [..."ABCDE"].map((name) => ({ name, status: "pass" })),
    },
    r3: {
      release_candidate: "R3",
      status: "VERIFIED_BASELINE",
      verification: {
        hard_gates: "PASS",
        evidence_packet_recovery: "PASS",
        durable_task_result: "PASS",
        primary_vault_modified: false,
      },
    },
    profiles,
    replayJournal: [1, 4, 8].map((day) => ({
      task_id: "rts01-high-automation-evidence-20261107-r4-observation-" + day,
      run_id: "run-" + day,
      operation_id: "op-" + day,
      observed_at: "2026-11-0" + day + "T03:00:00Z",
      source_snapshot_sha: R4_SOURCE_SNAPSHOT_SHA,
      result_commit: String(day).repeat(40),
      status: "done",
      e1_e5: "pass",
      remote_readback: "pass",
    })),
    registeredProjects: {
      kind: "registered_projects_evidence",
      schema_version: 1,
      source_snapshot_sha: R4_SOURCE_SNAPSHOT_SHA,
      generated_at: "2026-11-18T03:00:00Z",
      provenance: { ...context, run_id: "122" },
      status: "pass",
      arbitrary_commands: false,
      writes_forbidden: true,
      registered_projects: REGISTERED_PROJECT_IDS.map((id) => ({
        project_id: id,
        root: profiles.projects[id].root,
        profile_sha256: sha256(JSON.stringify(profiles.projects[id])),
        root_exists: true,
        status: "pass",
        fixed_tests: [{
          runner: "static_smoke", target: "index.html", timeout_sec: 30,
          status: "pass", ok: true, timed_out: false, exit_code: 0,
        }],
      })),
    },
    readback: { provenance: context },
    verifyCas: () => ({ task_id: "fixture-cas", trace_id: "trace-1" }),
    verifyObservation: (row) => Date.parse(row.observed_at),
    inputHashes: { replay_journal: "c".repeat(64) },
  };
}

test("synthetic complete evidence reaches READY only in the simulated formal context", () => {
  const evidence = fixture();
  assert.equal(assessHighAutomation(evidence).ready, true);
  const local = assessHighAutomation({ ...evidence, context: null });
  assert.equal(local.ready, false);
  assert.ok(local.reasons.includes("formal_runner_context_missing"));
});

test("missing formal evidence reports each missing input and stays NOT_READY", () => {
  const summary = assessHighAutomation({});
  assert.equal(summary.status, "MCP_HIGH_AUTOMATION_NOT_READY");
  assert.ok(summary.reasons.includes("missing_phase_evidence"));
  assert.ok(summary.reasons.includes("missing_replay_journal"));
  assert.ok(summary.reasons.includes("missing_registered_projects_evidence"));
  assert.ok(summary.reasons.includes("missing_cas_readback_evidence"));
});

test("an official validation branch carries runner provenance and stays ineligible for READY", () => {
  const ref = "refs/heads/codex/rts01-validation";
  const branchContext = runnerContext({
    GITHUB_ACTIONS: "true",
    GITHUB_SHA: context.workspace_sha,
    WHITE_STUDIO_RUNTIME_SHA: context.runtime_sha,
    GITHUB_RUN_ID: context.run_id,
    GITHUB_RUN_ATTEMPT: context.run_attempt,
    GITHUB_REPOSITORY: context.repository,
    GITHUB_REF: ref,
    RUNNER_ENVIRONMENT: "self-hosted",
  });
  assert.deepEqual(branchContext, { ...context, ref });
  const evidence = fixture();
  evidence.context = branchContext;
  evidence.phase.provenance = branchContext;
  evidence.readback.provenance = branchContext;
  evidence.registeredProjects.provenance.ref = ref;
  assert.deepEqual(assessHighAutomation(evidence).reasons, ["validation_ref_not_main"]);
});

test("replay uses the actual first and last observation and requires unique identities", () => {
  const evidence = fixture();
  evidence.replayJournal[2].observed_at = "2026-11-07T03:00:00Z";
  assert.ok(assessHighAutomation(evidence).reasons.includes("replay_observation_span_below_threshold"));
  evidence.replayJournal[2].run_id = evidence.replayJournal[0].run_id;
  assert.ok(assessHighAutomation(evidence).reasons.includes("replay_identity_duplicate"));
});

test("mismatched source or unavailable committed replay Result cannot pass", () => {
  const evidence = fixture();
  evidence.replayJournal[1].source_snapshot_sha = "f".repeat(64);
  assert.ok(assessHighAutomation(evidence).reasons.includes("replay_source_snapshot_mismatch"));
  evidence.replayJournal[1].source_snapshot_sha = R4_SOURCE_SNAPSHOT_SHA;
  evidence.verifyObservation = () => { throw new Error("missing Git object"); };
  assert.equal(assessHighAutomation(evidence).ready, false);
});

test("a seven-day journal cannot stretch a short interval between committed Results", () => {
  const evidence = fixture();
  evidence.verifyObservation = () => Date.parse("2026-11-01T02:59:00Z");
  const evaluation = assessHighAutomation(evidence);
  assert.equal(evaluation.replay.span_ms, 604800000);
  assert.equal(evaluation.replay.result_span_ms, 0);
  assert.ok(evaluation.reasons.includes("replay_result_span_below_threshold"));
});

test("checks eight exact profile results and their provenance instead of trusting pass", () => {
  const evidence = fixture();
  const projects = evidence.registeredProjects.registered_projects;
  projects[0].fixed_tests[0].target = "other.html";
  assert.ok(assessHighAutomation(evidence).reasons.includes("registered_project_fixed_test_mismatch:desktop-tutorial"));
  projects.pop();
  assert.ok(assessHighAutomation(evidence).reasons.includes("registered_project_set_incomplete"));
  evidence.registeredProjects.provenance = { ...context, runtime_sha: "c".repeat(40) };
  assert.ok(assessHighAutomation(evidence).reasons.includes("registered_projects_provenance_mismatch"));
});

test("rejects stale run provenance and a mismatched CAS readback", () => {
  const evidence = fixture();
  evidence.phase.provenance = { ...context, run_attempt: "1" };
  assert.ok(assessHighAutomation(evidence).reasons.includes("phase_provenance_mismatch"));
  evidence.verifyCas = () => { throw new Error("trace mismatch"); };
  assert.equal(assessHighAutomation(evidence).ready, false);
});

test("verifier rejects a stale recorder digest and an altered pass decision", () => {
  const input = fixture();
  const assessment = assessHighAutomation(input);
  const record = { schema_version: 1, kind: "mcp_high_automation_evidence", assessment, input_hashes: input.inputHashes };
  assert.equal(verifyRecordedEvidence(record, input).ready, true);
  const changed = { ...input, inputHashes: { replay_journal: "d".repeat(64) } };
  assert.ok(verifyRecordedEvidence(record, changed).reasons.includes("recorded_input_digest_mismatch"));
  const forged = { ...record, assessment: { ...assessment, ready: false } };
  assert.ok(verifyRecordedEvidence(forged, input).reasons.includes("recorded_assessment_mismatch"));
});

test("recorder and verifier CLI use real missing-input reports without writing a journal", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "rts01-evidence-cli-"));
  const output = path.join(root, "assessment.json");
  const journal = path.join(root, "absent.jsonl");
  const args = ["--output", output, "--journal", journal];
  const env = { ...process.env, VAULT_WORKSPACE_ROOT: root, GITHUB_ACTIONS: "false" };
  const run = (script) => spawnSync(process.execPath, [
    fileURLToPath(new URL("../src/" + script, import.meta.url)), ...args,
  ], { encoding: "utf8", env, timeout: 10000 });

  const recorder = run("record_high_automation_evidence.js");
  assert.equal(recorder.status, 0, recorder.stderr);
  const verifier = run("high_automation_gate.js");
  assert.equal(verifier.status, 1, verifier.stderr);
  assert.equal(JSON.parse(verifier.stdout).ready, false);
  assert.ok(JSON.parse(verifier.stdout).reasons.includes("missing_replay_journal"));
  assert.equal(JSON.parse(fs.readFileSync(output, "utf8")).assessment.ready, false);
  assert.equal(fs.existsSync(journal), false);
});

test("collector executes exactly eight bounded static fixtures and detects a missing project", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "rts01-registered-projects-test-"));
  const profiles = fixture().profiles;
  const missing = REGISTERED_PROJECT_IDS.at(-1);
  for (const id of REGISTERED_PROJECT_IDS) {
    if (id === missing) continue;
    const project = path.join(root, profiles.projects[id].root);
    fs.mkdirSync(project, { recursive: true });
    fs.writeFileSync(path.join(project, "index.html"), "<!doctype html><html><title>Fixture</title></html>\n");
  }
  fs.mkdirSync(path.join(root, "runtime"));
  fs.writeFileSync(path.join(root, "runtime", "test-profiles.json"), JSON.stringify(profiles));
  const before = collectRegisteredProjectsEvidence(root, context);
  assert.equal(before.status, "fail");
  assert.equal(before.registered_projects.find((project) => project.project_id === missing).root_exists, false);

  const finalProject = path.join(root, profiles.projects[missing].root);
  fs.mkdirSync(finalProject);
  fs.writeFileSync(path.join(finalProject, "index.html"), "<!doctype html><html><title>Fixture</title></html>\n");
  const collected = collectRegisteredProjectsEvidence(root, context);
  assert.equal(collected.status, "pass");
  assert.deepEqual(collected.registered_projects.map(({ project_id }) => project_id), REGISTERED_PROJECT_IDS);
  assert.deepEqual(checkRegisteredProjects(collected, profiles, context, Date.now()).reasons, []);
});
