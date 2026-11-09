
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