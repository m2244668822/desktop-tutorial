
test("analysis-only execution must not bypass the MCP protocol gate", () => {
  const executorSource = fs.readFileSync(path.join(here, "agentic_executor.js"), "utf8");
  assert.doesNotMatch(
    executorSource,
    /const mcpProtocolEvidence = analysisOnly\s*\?\s*\{\s*ok:\s*true,\s*evidence:\s*null\s*\}/,
  );
  assert.doesNotMatch(
    executorSource,
    /const mcpProtocolOk = analysisOnly \|\| mcpProtocolEvidence\.ok/,
  );
});
test("probe gives bounded calls enough time and requires complete evidence", () => {
  const probeSource = fs.readFileSync(path.join(here, "mcp_protocol_probe.js"), "utf8");
  assert.match(probeSource, /function request\([\s\S]*timeoutMs = 5000/);
  assert.match(probeSource, /setTimeout\(\(\) => \{[\s\S]*\}, timeoutMs\)/);
  assert.match(
    probeSource,
    /name: "runtime_run_test"[\s\S]*Math\.max\(5000, \(test\.timeoutSec \+ 5\) \* 1000\)/,
  );
  assert.match(
    probeSource,
    /const boundedOk =\s*evidence\.calls\.runtime_run_test\.length === tests\.length\s*&&/,
  );
});
test("Result reports MCP bounded validation only when the requested count is complete", () => {
  const executorSource = fs.readFileSync(path.join(here, "agentic_executor.js"), "utf8");
  assert.match(
    executorSource,
    /runtime_run_test\?\.length === testProfile\.tests\.length[\s\S]*runtime_run_test\.every/,
  );
});