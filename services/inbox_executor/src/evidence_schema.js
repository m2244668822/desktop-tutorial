import fs from "node:fs";

export class EvidenceValidationError extends Error {
  constructor(code, details = "") {
    super(details ? `${code}: ${details}` : code);
    this.name = "EvidenceValidationError";
    this.code = code;
  }
}

function fail(code, details = "") {
  throw new EvidenceValidationError(code, details);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function typeMatches(value, type) {
  if (Array.isArray(type)) return type.some((candidate) => typeMatches(value, candidate));
  if (type === "object") return isObject(value);
  if (type === "array") return Array.isArray(value);
  if (type === "string") return typeof value === "string";
  if (type === "boolean") return typeof value === "boolean";
  if (type === "integer") return Number.isInteger(value);
  if (type === "number") return typeof value === "number" && Number.isFinite(value);
  return true;
}

export function validateJsonSchema(value, schema, location = "$", errors = []) {
  if (schema.const !== undefined && JSON.stringify(value) !== JSON.stringify(schema.const)) {
    errors.push(`${location}: expected const ${JSON.stringify(schema.const)}`);
  }
  if (schema.enum && !schema.enum.some((item) => JSON.stringify(item) === JSON.stringify(value))) {
    errors.push(`${location}: value is not in enum`);
  }
  if (schema.type && !typeMatches(value, schema.type)) {
    errors.push(`${location}: expected ${schema.type}`);
    return errors;
  }
  if (schema.type === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) errors.push(`${location}: too short`);
    if (schema.pattern && !(new RegExp(schema.pattern).test(value))) errors.push(`${location}: pattern mismatch`);
    if (schema.format === "date-time" && Number.isNaN(Date.parse(value))) errors.push(`${location}: invalid date-time`);
  }
  if ((schema.type === "integer" || schema.type === "number") && schema.minimum !== undefined && value < schema.minimum) errors.push(`${location}: below minimum`);
  if ((schema.type === "integer" || schema.type === "number") && schema.maximum !== undefined && value > schema.maximum) errors.push(`${location}: above maximum`);
  if (schema.type === "array") {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push(`${location}: too few items`);
    if (schema.uniqueItems) {
      const serialized = value.map((item) => JSON.stringify(item));
      if (new Set(serialized).size !== serialized.length) errors.push(`${location}: duplicate items`);
    }
    if (schema.items) value.forEach((item, index) => validateJsonSchema(item, schema.items, `${location}[${index}]`, errors));
  }
  if (schema.type === "object") {
    for (const required of schema.required || []) {
      if (!(required in value)) errors.push(`${location}.${required}: required`);
    }
    for (const [key, child] of Object.entries(schema.properties || {})) {
      if (key in value) validateJsonSchema(value[key], child, `${location}.${key}`, errors);
    }
    if (schema.additionalProperties === false) {
      const allowed = new Set(Object.keys(schema.properties || {}));
      for (const key of Object.keys(value)) {
        if (!allowed.has(key)) errors.push(`${location}.${key}: additional property`);
      }
    }
  }
  return errors;
}

export function assertJsonSchema(value, schema, label = "evidence") {
  const errors = validateJsonSchema(value, schema);
  if (errors.length) fail(`${label}_schema_invalid`, errors.join("; "));
  return value;
}

export function readJsonSchema(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

const REPLAY_MIN_SPAN_MS = 604800000;

function assertCommonPacket(packet, kind) {
  if (!isObject(packet)) fail("evidence_packet_not_object");
  if (packet.schema_version !== 1) fail("evidence_schema_version_invalid");
  if (packet.kind !== kind) fail("evidence_kind_invalid");
  if (typeof packet.generated_at !== "string" || Number.isNaN(Date.parse(packet.generated_at))) fail("evidence_generated_at_invalid");
  if (typeof packet.source_snapshot_sha !== "string" || packet.source_snapshot_sha.length < 7) fail("source_snapshot_sha_missing");
}

export function validateRegisteredProjectsEvidence(packet, { expectedProjectIds = [] } = {}) {
  assertCommonPacket(packet, "registered_projects_evidence");
  if (!Array.isArray(packet.registered_projects)) fail("registered_projects_missing");
  const actual = packet.registered_projects.map((item) => item?.project_id);
  if (new Set(actual).size !== actual.length) fail("registered_project_duplicate");
  const expected = [...expectedProjectIds].sort();
  const received = [...actual].sort();
  if (expected.length && JSON.stringify(expected) !== JSON.stringify(received)) fail("registered_project_set_incomplete");
  if (!["pass", "fail"].includes(packet.status)) fail("registered_projects_status_invalid");
  if (packet.arbitrary_commands !== false) fail("registered_projects_arbitrary_commands_enabled");
  if (packet.writes_forbidden !== true) fail("registered_projects_write_boundary_missing");
  for (const project of packet.registered_projects) {
    if (!isObject(project) || typeof project.project_id !== "string") fail("registered_project_record_invalid");
    if (typeof project.root !== "string" || typeof project.profile_sha256 !== "string") fail("registered_project_provenance_missing");
    if (typeof project.root_exists !== "boolean") fail("registered_project_root_state_missing");
    if (!Array.isArray(project.fixed_tests) || project.fixed_tests.length === 0) fail("registered_project_fixed_tests_missing");
    for (const fixedTest of project.fixed_tests) {
      if (!isObject(fixedTest) || typeof fixedTest.runner !== "string" || typeof fixedTest.target !== "string") fail("registered_project_test_record_invalid");
      if (!Number.isInteger(fixedTest.timeout_sec) || fixedTest.timeout_sec < 1 || fixedTest.timeout_sec > 120) fail("registered_project_timeout_invalid");
      if (!["pass", "fail", "timeout", "blocked"].includes(fixedTest.status)) fail("registered_project_test_status_invalid");
      if (typeof fixedTest.ok !== "boolean" || typeof fixedTest.timed_out !== "boolean") fail("registered_project_test_result_invalid");
    }
  }
  return packet;
}

export function validateLongTermReplayEvidence(packet, { expectedSourceSnapshotSha = "" } = {}) {
  assertCommonPacket(packet, "long_term_replay_evidence");
  if (packet.required_runs !== 3) fail("replay_required_runs_invalid");
  if (packet.min_span_ms !== REPLAY_MIN_SPAN_MS) fail("replay_min_span_invalid");
  if (!Array.isArray(packet.observations)) fail("replay_observations_missing");
  if (!["pass", "not_ready", "fail"].includes(packet.status)) fail("replay_status_invalid");
  if (packet.append_only !== true) fail("replay_append_only_missing");
  if (expectedSourceSnapshotSha && packet.source_snapshot_sha !== expectedSourceSnapshotSha) fail("replay_source_snapshot_mismatch");

  const seen = { task_id: new Set(), run_id: new Set(), operation_id: new Set() };
  for (const observation of packet.observations) {
    if (!isObject(observation)) fail("replay_observation_invalid");
    for (const identity of Object.keys(seen)) {
      const value = observation[identity];
      if (typeof value !== "string" || !value) fail(`replay_${identity}_missing`);
      if (seen[identity].has(value)) fail("replay_identity_duplicate");
      seen[identity].add(value);
    }
    if (typeof observation.observed_at !== "string" || Number.isNaN(Date.parse(observation.observed_at))) fail("replay_observed_at_invalid");
    if (observation.source_snapshot_sha !== packet.source_snapshot_sha || (expectedSourceSnapshotSha && observation.source_snapshot_sha !== expectedSourceSnapshotSha)) fail("replay_source_snapshot_mismatch");
    if (observation.status !== "done" || observation.e1_e5 !== "pass" || observation.remote_readback !== "pass") fail("replay_observation_not_verified");
    if (typeof observation.result_commit !== "string" || !observation.result_commit) fail("replay_result_commit_missing");
  }

  if (packet.status === "pass") {
    if (packet.observations.length < packet.required_runs) fail("replay_observation_count_below_threshold");
    const times = packet.observations.map((item) => Date.parse(item.observed_at));
    const span = Math.max(...times) - Math.min(...times);
    if (span < packet.min_span_ms) fail("replay_observation_span_below_threshold");
  }
  return packet;
}

export { REPLAY_MIN_SPAN_MS };
