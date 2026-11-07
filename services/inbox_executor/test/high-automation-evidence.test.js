import assert from "node:assert/strict";
import test from "node:test";
import {
  buildHighAutomationEvidence,
  casResultWritebackPass,
  resultEvidence,
} from "../src/record_high_automation_evidence.js";

const sourceSnapshotSha = "7f7f2faeddf78521402be5e30cf6cf1cec638358565405d4348c992e81c63a4e";
const registeredProjectIds = [
  "desktop-tutorial",
  "automation-fixture",
  "white-studio-thunder-arcade",
  "white-studio-web",
  "white-studio-games",
  "white-studio-palette-creator",
  "white-studio-game-contributor-kit",
  "partner-site-demo",
];

function taskResult(status, remoteRevision = "revision-1") {
  return `- task_id：\`task-1\`
- run_id：\`run-1\`
- operation_id：\`op-1\`
- lease_id：\`lease-1\`
- lease_generation：1
- fencing_token：\`fence-1\`
- remote_task_revision：\`${remoteRevision}\`
- 結果：${status}
- identity_validation：\`executor_identity_match\``;
}

function registeredProjectsPacket(status = "pass") {
  return {
    schema_version: 1,
    kind: "registered_projects_evidence",
    generated_at: "2026-11-07T00:00:00.000Z",
    source_snapshot_sha: sourceSnapshotSha,
    registered_projects: registeredProjectIds.map((project_id) => ({
      project_id,
      root: project_id,
      profile_sha256: "profile-sha-1234567",
      source_scope: "runtime/test-profiles.json",
      root_exists: true,
      fixed_tests: [{ runner: "static_smoke", target: "index.html", timeout_sec: 30, status: "pass", ok: true, timed_out: false }],
      status: "pass",
    })),
    status,
    reasons: status === "pass" ? [] : ["registered_project_fixed_test_failed"],
    arbitrary_commands: false,
    writes_forbidden: true,
  };
}

function replayPacket(count = 2, status = "not_ready") {
  return {
    schema_version: 1,
    kind: "long_term_replay_evidence",
    generated_at: "2026-11-07T00:00:00.000Z",
    source_snapshot_sha: sourceSnapshotSha,
    required_runs: 3,
    min_span_ms: 604800000,
    observations: Array.from({ length: count }, (_, index) => ({
      task_id: `task-${index + 1}`,
      run_id: `run-${index + 1}`,
      operation_id: `operation-${index + 1}`,
      observed_at: index === 0 ? "2026-11-07T00:00:00.000Z" : index === 1 ? "2026-11-10T00:00:00.000Z" : "2026-11-14T00:00:00.000Z",
      source_snapshot_sha: sourceSnapshotSha,
      status: "done",
      e1_e5: "pass",
      result_commit: `result-${index + 1}`,
      remote_readback: "pass",
    })),
    status,
    reasons: status === "pass" ? [] : ["replay_observation_count_below_threshold"],
    append_only: true,
  };
}

const phase = { phases: Object.fromEntries(["A", "B", "C", "D", "E"].map((name) => [name, { status: "pass" }])) };
const r3 = {
  status: "VERIFIED_BASELINE",
  verification: {
    hard_gates: "PASS",
    evidence_packet_recovery: "PASS",
    durable_task_result: "PASS",
    primary_vault_modified: false,
  },
};

test("recorder rejects missing high-automation evidence packets", () => {
  assert.throws(
    () => buildHighAutomationEvidence({ phase, taskText: taskResult("done"), r3, sourceSnapshotSha }),
    /registered_projects_packet_missing/,
  );
});

test("recorder preserves registered pass and replay not-ready as separate gate inputs", () => {
  const registered = registeredProjectsPacket("pass");
  const replay = replayPacket(2, "not_ready");
  const evidence = buildHighAutomationEvidence({
    phase,
    taskText: taskResult("done"),
    r3,
    sourceSnapshotSha,
    registeredProjects: registered,
    longTermReplay: replay,
  });
  assert.deepEqual(evidence.registered_projects, registered);
  assert.deepEqual(evidence.long_term_replay, replay);
  assert.equal(evidence.registered_projects.status, "pass");
  assert.equal(evidence.long_term_replay.status, "not_ready");
});

test("recorder accepts a validated three-run seven-day replay packet", () => {
  const registered = registeredProjectsPacket("pass");
  const replay = replayPacket(3, "pass");
  const evidence = buildHighAutomationEvidence({
    phase,
    taskText: taskResult("done"),
    r3,
    sourceSnapshotSha,
    registeredProjects: registered,
    longTermReplay: replay,
  });
  assert.equal(evidence.long_term_replay.status, "pass");
  assert.equal(evidence.registered_projects.status, "pass");
  assert.equal(evidence.gates.r3_baseline, "pass");
});

test("CAS writeback passes for a durable blocked Result with a complete claim", () => {
  const result = resultEvidence(taskResult("blocked"));
  assert.equal(result.claim_identity_complete, true);
  assert.equal(casResultWritebackPass(result), true);
});

test("CAS writeback rejects an incomplete or failed Result", () => {
  const result = resultEvidence(taskResult("failed", ""));
  assert.equal(result.claim_identity_complete, false);
  assert.equal(casResultWritebackPass(result), false);
});
