import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  appendReplayObservation,
  evaluateReplayEvidence,
  observationFromTask,
} from "../src/long_term_replay_evidence.js";

const sourceSnapshotSha = "7f7f2faeddf78521402be5e30cf6cf1cec638358565405d4348c992e81c63a4e";

function journalFixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "rts01-replay-"));
  return { root, journalPath: path.join(root, "replay.jsonl") };
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
    observed_sanitized_trace: "must-not-be-persisted",
    ...overrides,
  };
}

function cleanup(root) {
  fs.rmSync(root, { recursive: true, force: true });
}

test("three valid observations pass only after the seven-day span", () => {
  const fixture = journalFixture();
  try {
    appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(1, "2026-11-07T00:00:00.000Z") });
    appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(2, "2026-11-10T00:00:00.000Z") });
    const result = appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(3, "2026-11-14T00:00:00.000Z") });
    assert.equal(result.status, "pass");
    assert.equal(result.observations.length, 3);
    assert.equal(result.reasons.length, 0);
  } finally {
    cleanup(fixture.root);
  }
});

test("duplicate run or operation identity cannot be appended", () => {
  const fixture = journalFixture();
  try {
    appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(1, "2026-11-07T00:00:00.000Z") });
    assert.throws(
      () => appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(1, "2026-11-08T00:00:00.000Z") }),
      /replay_identity_duplicate/,
    );
  } finally {
    cleanup(fixture.root);
  }
});

test("source snapshot mismatch cannot be appended", () => {
  const fixture = journalFixture();
  try {
    appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(1, "2026-11-07T00:00:00.000Z") });
    assert.throws(
      () => appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(2, "2026-11-08T00:00:00.000Z", { source_snapshot_sha: "different-source" }) }),
      /replay_source_snapshot_mismatch/,
    );
  } finally {
    cleanup(fixture.root);
  }
});

test("two observations remain not ready", () => {
  const fixture = journalFixture();
  try {
    appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(1, "2026-11-07T00:00:00.000Z") });
    appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(2, "2026-11-14T00:00:00.000Z") });
    const result = evaluateReplayEvidence({ journalPath: fixture.journalPath, expectedSourceSnapshotSha: sourceSnapshotSha });
    assert.equal(result.status, "not_ready");
    assert.ok(result.reasons.includes("replay_observation_count_below_threshold"));
  } finally {
    cleanup(fixture.root);
  }
});

test("the seven-day boundary is exact and journal writes are append-only", () => {
  const fixture = journalFixture();
  try {
    appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(1, "2026-11-07T00:00:00.000Z") });
    appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(2, "2026-11-10T00:00:00.000Z") });
    const beforeThird = fs.readFileSync(fixture.journalPath, "utf8");
    const belowBoundary = appendReplayObservation({ journalPath: fixture.journalPath, observation: observation(3, "2026-11-13T23:59:59.999Z") });
    assert.equal(belowBoundary.status, "not_ready");
    assert.ok(belowBoundary.reasons.includes("replay_observation_span_below_threshold"));
    const afterThird = fs.readFileSync(fixture.journalPath, "utf8");
    assert.ok(afterThird.startsWith(beforeThird));
    assert.equal(afterThird.split(/\r?\n/).filter(Boolean).length, 3);
    assert.doesNotMatch(afterThird, /observed_sanitized_trace/);
  } finally {
    cleanup(fixture.root);
  }
});

test("task Result is reduced to replay metadata without copying the trace", () => {
  const fixture = journalFixture();
  try {
    const taskPath = path.join(fixture.root, "task.md");
    fs.writeFileSync(taskPath, [
      "- task_id：`rts01-high-automation-evidence-20261107-r4`",
      "- run_id：`run-1`",
      "- operation_id：`operation-1`",
      "- source_snapshot_sha：`" + sourceSnapshotSha + "`",
      "- 結果：done",
      "- identity_validation：`executor_identity_match`",
      "- E5 remote readback：`pass`",
      "```text",
      "SECRET_AND_FULL_TRACE_MUST_NOT_BE_COPIED",
      "```",
    ].join("\n"), "utf8");
    const observation = observationFromTask({
      taskPath,
      sourceSnapshotSha,
      resultCommit: "result-1",
      observedAt: "2026-11-07T00:00:00.000Z",
    });
    const packet = appendReplayObservation({ journalPath: fixture.journalPath, observation });
    assert.equal(packet.observations[0].status, "done");
    assert.equal(Object.hasOwn(packet.observations[0], "observed_sanitized_trace"), false);
    assert.doesNotMatch(fs.readFileSync(fixture.journalPath, "utf8"), /SECRET_AND_FULL_TRACE/);
  } finally {
    cleanup(fixture.root);
  }
});
