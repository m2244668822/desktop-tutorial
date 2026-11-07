import assert from "node:assert/strict";
import test from "node:test";
import { casResultWritebackPass, resultEvidence } from "../src/record_high_automation_evidence.js";

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
