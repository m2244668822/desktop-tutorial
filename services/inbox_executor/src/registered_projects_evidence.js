import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { VaultWorkspace } from "../../vault_workspace_mcp/src/workspace.js";
import { runnerContext } from "./high_automation_evidence.js";
import { readGitRevision } from "./result_readback.js";
import { REGISTERED_PROJECT_IDS, R4_SOURCE_SNAPSHOT_SHA, sha256 } from "./r4_evidence.js";

function insideProjectRoot(repoRoot, relativePath) {
  if (!relativePath || path.isAbsolute(relativePath)) return false;
  try {
    const target = fs.realpathSync(path.resolve(repoRoot, relativePath));
    const relative = path.relative(fs.realpathSync(repoRoot), target);
    return Boolean(relative) && !relative.startsWith("..") && !path.isAbsolute(relative) &&
      fs.statSync(target).isDirectory();
  } catch {
    return false;
  }
}

function runFixedTest(workspace, profile, { runner, target, timeoutSec }) {
  const test = {
    runner, target, timeout_sec: timeoutSec,
    status: "blocked", ok: false, timed_out: false, exit_code: null,
  };
  if (typeof runner !== "string" || typeof target !== "string" ||
      !Number.isInteger(timeoutSec) || timeoutSec < 1 || timeoutSec > 120) {
    return { ...test, error_code: "invalid_fixed_test_profile" };
  }
  try {
    const result = workspace.runTest({ projectDir: profile.root, runner, target, timeoutSec });
    const ok = result.ok === true && result.exit_code === 0 && result.timed_out === false;
    return {
      ...test,
      status: result.timed_out ? "timeout" : ok ? "pass" : "fail",
      ok,
      timed_out: result.timed_out === true,
      exit_code: result.exit_code,
    };
  } catch (error) {
    return { ...test, error_code: error.code || "runtime_test_error" };
  }
}

export function collectRegisteredProjectsEvidence(repoRoot, provenance) {
  const profiles = JSON.parse(fs.readFileSync(path.join(repoRoot, "runtime", "test-profiles.json"), "utf8"));
  if (profiles.policy?.arbitrary_shell !== false) throw new Error("registered_project_policy_unsafe");
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "rts01-registered-tests-"));
  const workspace = new VaultWorkspace({
    workspaceRoot: repoRoot,
    auditDir: path.join(scratch, "audit"),
    trashDir: path.join(scratch, "trash"),
    autoApprove: false,
  });

  const registeredProjects = REGISTERED_PROJECT_IDS.map((projectId) => {
    const profile = profiles.projects?.[projectId];
    const rootExists = insideProjectRoot(repoRoot, profile?.root);
    const fixedTests = rootExists && profile.automation_mode === "bounded_write" && Array.isArray(profile.tests)
      ? profile.tests.map((test) => runFixedTest(workspace, profile, test || {}))
      : [];
    return {
      project_id: projectId,
      root: profile?.root ?? "",
      profile_sha256: profile ? sha256(JSON.stringify(profile)) : null,
      root_exists: rootExists,
      status: fixedTests.length && fixedTests.every((test) => test.ok) ? "pass" : "fail",
      fixed_tests: fixedTests,
    };
  });

  return {
    schema_version: 1,
    kind: "registered_projects_evidence",
    source_snapshot_sha: R4_SOURCE_SNAPSHOT_SHA,
    generated_at: new Date().toISOString(),
    provenance,
    status: registeredProjects.every((project) => project.status === "pass") ? "pass" : "fail",
    arbitrary_commands: false,
    writes_forbidden: true,
    registered_projects: registeredProjects,
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const { values } = parseArgs({ options: { output: { type: "string" } } });
    if (!values.output) throw new Error("registered_projects_output_path_required");
    const root = path.resolve(process.env.VAULT_WORKSPACE_ROOT || fileURLToPath(new URL("../../../../../", import.meta.url)));
    const output = path.resolve(values.output);
    const provenance = runnerContext();
    if (provenance && (readGitRevision(root, "HEAD") !== provenance.workspace_sha ||
        readGitRevision(path.join(root, "runtime", "desktop-tutorial"), "HEAD") !== provenance.runtime_sha ||
        readGitRevision(root, "HEAD:runtime/desktop-tutorial") !== provenance.runtime_sha)) {
      throw new Error("registered_projects_checkout_mismatch");
    }
    const packet = collectRegisteredProjectsEvidence(root, provenance);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, JSON.stringify(packet, null, 2) + "\n", { encoding: "utf8", flag: "wx" });
    console.log(JSON.stringify({ output, status: packet.status, project_count: packet.registered_projects.length }));
    process.exitCode = packet.status === "pass" ? 0 : 1;
  } catch (error) {
    console.error(error.message);
    process.exitCode = 2;
  }
}
