import assert from "node:assert/strict";
import { processConversationEvent } from "./conversation_event.js";

const sample = {
  event_id: "conv-demo-001",
  conversation_id: "health-research-demo",
  turn_id: "turn-17",
  actor: "user",
  occurred_at: "2026-11-04T13:45:00+08:00",
  source_system: "chatgpt",
  event_kind: "task_request",
  text: "目前先做到可以實際互動跟處理的應用，基本上交給你處理。",
  proposals: {
    user_claims: [
      {
        claim: "使用者目前優先希望先完成可實際互動與資料處理的應用。",
        claim_type: "goal",
        epistemic_status: "KNOWN",
        confidence: 1,
        lifecycle_status: "APPROVED"
      }
    ],
    actions: [
      {
        action_type: "SEARCH",
        target: "historical project data",
        requested_scope: "find relevant prior evidence"
      },
      {
        action_type: "UPDATE_USER_MODEL",
        target: "user model",
        requested_scope: "stage the new priority"
      },
      {
        action_type: "EXPAND_PERMISSION",
        target: "agent authority",
        requested_scope: "allow future writes without approval"
      }
    ],
    task: {
      task_id: "conversation-event-mvp-demo",
      task_goal: "stage and govern one conversation event"
    }
  }
};

const result = processConversationEvent(sample);

assert.equal(result.user_claim_candidates.length, 1);
assert.equal(result.user_claim_candidates[0].epistemic_status, "KNOWN");
assert.equal(result.user_claim_candidates[0].lifecycle_status, "CANDIDATE");
assert.deepEqual(result.user_claim_candidates[0].source_refs, ["conv-demo-001"]);

assert.equal(result.permission_decisions.length, 3);
assert.equal(result.permission_decisions[0].permission_state, "ALLOW");
assert.equal(result.permission_decisions[1].permission_state, "REQUIRE_APPROVAL");
assert.equal(result.permission_decisions[2].permission_state, "DENY");

assert.equal(result.task_result.task_id, "conversation-event-mvp-demo");
assert.equal(result.task_result.result_status, "UNVERIFIED");
assert.deepEqual(result.task_result.evidence_refs, []);

assert.throws(
  () =>
    processConversationEvent({
      ...sample,
      event_id: "bad-confidence",
      proposals: {
        user_claims: [
          {
            claim: "invalid confidence",
            claim_type: "goal",
            epistemic_status: "INFERRED",
            confidence: 1.5
          }
        ]
      }
    }),
  /invalid_confidence/
);

console.log("CONVERSATION_EVENT_E2E_PASS");
