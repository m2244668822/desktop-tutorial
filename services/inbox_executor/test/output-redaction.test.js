import assert from "node:assert/strict";
import test from "node:test";
import { upsertNamedResult } from "../src/inbox.js";
import { sanitizeSensitiveOutput } from "../src/output_redaction.js";

// Build the invalid fixture at runtime so repository secret scanners do not
// mistake the test source itself for a live credential.
const syntheticOpenAiKey = [
  "sk",
  "proj",
  "SYNTHETIC_ONLY_NOT_VALID_0123456789",
].join("-");
const syntheticBasic = "U1lOVEhFVElDX09OTFk6Tk9UX1ZBTElE";

test("redacts synthetic credentials before Result persistence", () => {
  const input = [
    `agent_output=${syntheticOpenAiKey}`,
    `Authorization: Basic ${syntheticBasic}`,
    `publish_error: OPENAI_API_KEY=${syntheticOpenAiKey}`,
  ].join("\n");

  const output = sanitizeSensitiveOutput(input);

  assert.equal(output.includes(syntheticOpenAiKey), false);
  assert.equal(output.includes(syntheticBasic), false);
  assert.match(output, /\[REDACTED_CREDENTIAL\]/);
  assert.match(output, /Authorization: \[REDACTED_CREDENTIAL\]/i);
});

test("redacts credentials embedded in exception text without hiding the error family", () => {
  const input = `git_push_failed: Authorization: Bearer ${syntheticOpenAiKey}`;
  const output = sanitizeSensitiveOutput(input);

  assert.equal(output.includes(syntheticOpenAiKey), false);
  assert.match(output, /^git_push_failed:/);
  assert.match(output, /Authorization: \[REDACTED_CREDENTIAL\]/i);
});

test("redacts quoted authorization values and generic secret assignments", () => {
  const genericSecret = "SYNTHETIC_ONLY_NOT_VALID_GENERIC_SECRET_0123456789";
  const input = [
    `Authorization: Bearer "${genericSecret}"`,
    `CODEX_API_KEY=${genericSecret}`,
    `GITHUB_TOKEN='${genericSecret}'`,
  ].join("\n");

  const output = sanitizeSensitiveOutput(input);

  assert.equal(output.includes(genericSecret), false);
  assert.match(output, /CODEX_API_KEY=\[REDACTED_CREDENTIAL\]/);
  assert.match(output, /GITHUB_TOKEN=\[REDACTED_CREDENTIAL\]/);
});

test("preserves ordinary diagnostics", () => {
  const input = "no_headless_executor_ready: CODEX_HOME is not readable";
  assert.equal(sanitizeSensitiveOutput(input), input);
});

test("all named Result writers redact before persistence", () => {
  const source = "---\nstatus: running\n---\n\n## 現在這一份契約\n\nTask-ID: synthetic\n";
  const result = upsertNamedResult(
    source,
    "## Result（synthetic 回寫）",
    `- agent_output：${syntheticOpenAiKey}`,
  );

  assert.equal(result.includes(syntheticOpenAiKey), false);
  assert.match(result, /agent_output：\[REDACTED_CREDENTIAL\]/);
});
