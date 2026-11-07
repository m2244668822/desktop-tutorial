import assert from "node:assert/strict";
import test from "node:test";
import {
  validateRegisteredProjectsEvidence,
  validateLongTermReplayEvidence,
} from "../src/evidence_schema.js";

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

function registeredPacket(projects = registeredProjectIds) {
  return {
    schema_version: 1,
    kind: "registered_projects_evidence",
    generated_at: "2026-11-07T00:00:00.000Z",
    source_snapshot_sha: sourceSnapshotSha,
    registered_projects: projects.map((project_id) => ({
      project_id,
      root: project_id === "desktop-tutorial" ? "runtime/desktop-tutorial" : project_id === "automation-fixture" ? "runtime/.mcp-automation-fixture" : project_id,
      profile_sha256: `profile-${project_id}`,
      root_exists: true,
      fixed_tests: [{
        runner: "static_smoke",
        target: "index.html",
        timeout_sec: 30,
        status: "pass",
        ok: true,
        timed_out: false,
      }],
      status: "pass",
    })),
    status: "pass",
    reasons: [],
    arbitrary_commands: false,
    writes_forbidden: true,
  };
}

function replayPacket(observations) {
  return {
    schema_version: 1,
    kind: "long_term_replay_evidence",
    generated_at: "2026-11-07T00:00:00.000Z",
    source_snapshot_sha: sourceSnapshotSha,
    required_runs: 3,
    min_span_ms: 604800000,
    observations,
    status: "pass",
    reasons: [],
    append_only: true,
  };
}

function observation(index, observedAt, overrides = {}) {
  return {
    task_id: `rts01-high-automation-evidence-20261107-r4-${index}`,
    run_id: `run-${index}`,
    operation_id: `operation-${index}`,
    observed_at: observedAt,
    source_snapshot_sha: sourceSnapshotSha,
    status: "done",
    e1_e5: "pass",
    result_commit: `result-${index}`,
    remote_readback: "pass",
    ...overrides,
  };
}

test("registered-project evidence rejects a missing required project", () => {
  const packet = registeredPacket(registeredProjectIds.slice(0, -1));
  assert.throws(
    () => validateRegisteredProjectsEvidence(packet, { expectedProjectIds: registeredProjectIds }),
    /registered_project_set_incomplete/,
  );
});

test("long-term replay rejects duplicate run or operation identity", () => {
  const packet = replayPacket([
    observation(1, "2026-11-07T00:00:00.000Z"),
    observation(1, "2026-11-10T00:00:00.000Z"),
    observation(3, "2026-11-14T00:00:00.000Z"),
  ]);
  assert.throws(
    () => validateLongTermReplayEvidence(packet, { expectedSourceSnapshotSha: sourceSnapshotSha }),
    /replay_identity_duplicate/,
  );
});

test("long-term replay rejects an observation from another source snapshot", () => {
  const packet = replayPacket([
    observation(1, "2026-11-07T00:00:00.000Z"),
    observation(2, "2026-11-10T00:00:00.000Z", { source_snapshot_sha: "different-source" }),
    observation(3, "2026-11-14T00:00:00.000Z"),
  ]);
  assert.throws(
    () => validateLongTermReplayEvidence(packet, { expectedSourceSnapshotSha: sourceSnapshotSha }),
    /replay_source_snapshot_mismatch/,
  );
});

test("long-term replay rejects three observations before the seven-day span", () => {
  const packet = replayPacket([
    observation(1, "2026-11-07T00:00:00.000Z"),
    observation(2, "2026-11-08T00:00:00.000Z"),
    observation(3, "2026-11-13T23:59:59.999Z"),
  ]);
  assert.throws(
    () => validateLongTermReplayEvidence(packet, { expectedSourceSnapshotSha: sourceSnapshotSha }),
    /replay_observation_span_below_threshold/,
  );
});

test("registered-project evidence rejects pass status when a project test failed", () => {
  const packet = registeredPacket();
  packet.registered_projects[0].status = "fail";
  packet.registered_projects[0].fixed_tests[0].status = "fail";
  assert.throws(
    () => validateRegisteredProjectsEvidence(packet, { expectedProjectIds: registeredProjectIds }),
    /registered_projects_status_inconsistent/,
  );
});

test("replay evidence rejects not-ready status without an exact threshold reason", () => {
  const packet = replayPacket([
    observation(1, "2026-11-07T00:00:00.000Z"),
    observation(2, "2026-11-10T00:00:00.000Z"),
  ]);
  packet.status = "not_ready";
  packet.reasons = [];
  assert.throws(
    () => validateLongTermReplayEvidence(packet, { expectedSourceSnapshotSha: sourceSnapshotSha }),
    /replay_not_ready_reason_missing/,
  );
});
