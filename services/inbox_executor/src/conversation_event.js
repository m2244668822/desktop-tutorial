export const POLICY_VERSION = "conversation-governance-v0.1";

export const CLAIM_TYPES = new Set([
  "preference",
  "goal",
  "knowledge_state",
  "interaction_style",
  "constraint",
  "value",
  "strategy",
]);

export const EPISTEMIC_STATUSES = new Set([
  "KNOWN",
  "INFERRED",
  "UNKNOWN",
  "CONFLICTED",
]);

export const ACTION_POLICY = new Map([
  ["READ", "ALLOW"],
  ["SEARCH", "ALLOW"],
  ["INFER", "ALLOW"],
  ["PROPOSE", "ALLOW"],
  ["UPDATE_USER_MODEL", "REQUIRE_APPROVAL"],
  ["WRITE_KNOWLEDGE", "REQUIRE_APPROVAL"],
  ["MODIFY_FILE", "REQUIRE_APPROVAL"],
  ["DELETE", "DENY"],
  ["CHANGE_POLICY", "DENY"],
  ["EXPAND_PERMISSION", "DENY"],
]);

function requireString(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw Object.assign(new Error(`invalid_${field}`), {
      code: `invalid_${field}`,
    });
  }
  return value.trim();
}

function finiteConfidence(value, fallback = 0.5) {
  const n = value == null ? fallback : Number(value);
  if (!Number.isFinite(n) || n < 0 || n > 1) {
    throw Object.assign(new Error("invalid_confidence"), {
      code: "invalid_confidence",
    });
  }
  return n;
}

export function normalizeConversationEvent(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw Object.assign(new Error("invalid_event"), { code: "invalid_event" });
  }

  const actor = requireString(input.actor, "actor");
  if (!["user", "assistant", "system"].includes(actor)) {
    throw Object.assign(new Error("invalid_actor"), { code: "invalid_actor" });
  }

  const event = {
    schema_version: "0.1",
    policy_version: POLICY_VERSION,
    event_id: requireString(input.event_id, "event_id"),
    conversation_id: requireString(input.conversation_id, "conversation_id"),
    turn_id: requireString(input.turn_id, "turn_id"),
    actor,
    occurred_at: requireString(input.occurred_at, "occurred_at"),
    source_system: requireString(input.source_system || "chatgpt", "source_system"),
    text: requireString(input.text, "text"),
    event_kind: requireString(input.event_kind || "observation", "event_kind"),
    proposals:
      input.proposals && typeof input.proposals === "object" && !Array.isArray(input.proposals)
        ? input.proposals
        : {},
  };

  return event;
}

export function stageUserClaims(event) {
  const claims = Array.isArray(event.proposals.user_claims)
    ? event.proposals.user_claims
    : [];

  return claims.map((raw, index) => {
    const claimType = requireString(raw.claim_type, "claim_type");
    if (!CLAIM_TYPES.has(claimType)) {
      throw Object.assign(new Error(`invalid_claim_type:${claimType}`), {
        code: "invalid_claim_type",
      });
    }

    const epistemicStatus = requireString(
      raw.epistemic_status || "INFERRED",
      "epistemic_status"
    );
    if (!EPISTEMIC_STATUSES.has(epistemicStatus)) {
      throw Object.assign(
        new Error(`invalid_epistemic_status:${epistemicStatus}`),
        { code: "invalid_epistemic_status" }
      );
    }

    return {
      schema_version: "0.1",
      policy_version: POLICY_VERSION,
      claim_id: raw.claim_id || `${event.event_id}:claim:${index + 1}`,
      claim: requireString(raw.claim, "claim"),
      claim_type: claimType,
      epistemic_status: epistemicStatus,
      lifecycle_status: "CANDIDATE",
      confidence: finiteConfidence(raw.confidence),
      source_refs: [event.event_id],
      evidence_summary:
        typeof raw.evidence_summary === "string" ? raw.evidence_summary.trim() : "",
      counterevidence_refs: Array.isArray(raw.counterevidence_refs)
        ? raw.counterevidence_refs.filter((x) => typeof x === "string" && x.trim())
        : [],
      supersedes:
        typeof raw.supersedes === "string" && raw.supersedes.trim()
          ? raw.supersedes.trim()
          : null,
      created_from_turn: event.turn_id,
    };
  });
}

export function decidePermissions(event) {
  const actions = Array.isArray(event.proposals.actions)
    ? event.proposals.actions
    : [];

  return actions.map((raw, index) => {
    const actionType = requireString(raw.action_type, "action_type");
    const permissionState = ACTION_POLICY.get(actionType) || "DENY";

    return {
      schema_version: "0.1",
      policy_version: POLICY_VERSION,
      decision_id: raw.decision_id || `${event.event_id}:permission:${index + 1}`,
      action_type: actionType,
      target:
        typeof raw.target === "string" && raw.target.trim() ? raw.target.trim() : null,
      requested_scope:
        typeof raw.requested_scope === "string" ? raw.requested_scope.trim() : "",
      permission_state: permissionState,
      policy_basis:
        permissionState === "ALLOW"
          ? "bounded_low_risk_action"
          : permissionState === "REQUIRE_APPROVAL"
            ? "human_authority_required"
            : "authority_expansion_or_destructive_action_denied",
      requested_by: event.actor,
      approved_by: null,
      approval_time: null,
      execution_id: null,
      result: permissionState === "DENY" ? "blocked" : "pending",
    };
  });
}

export function buildTaskResultSkeleton(event) {
  const task = event.proposals.task;
  if (!task || typeof task !== "object" || Array.isArray(task)) return null;

  return {
    schema_version: "0.1",
    policy_version: POLICY_VERSION,
    task_id: requireString(task.task_id, "task_id"),
    task_goal: requireString(task.task_goal, "task_goal"),
    claimed_result: "",
    result_status: "UNVERIFIED",
    actions_attempted: [],
    actions_completed: [],
    evidence_refs: [],
    verification_method: null,
    verification_result: null,
    remaining_unknowns: [],
    failures: [],
    blocked_reasons: [],
    side_effects: [],
    rollback_available: null,
    source_event_id: event.event_id,
  };
}

export function processConversationEvent(input) {
  const event = normalizeConversationEvent(input);
  return {
    event,
    user_claim_candidates: stageUserClaims(event),
    permission_decisions: decidePermissions(event),
    task_result: buildTaskResultSkeleton(event),
  };
}
