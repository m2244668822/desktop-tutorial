import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { collectRegisteredProjectsEvidence, REGISTERED_PROJECT_IDS } from "../src/registered_projects_evidence.js";

const sourceSnapshotSha = "7f7f2faeddf78521402be5e30cf6cf1cec638358565405d4348c992e81c63a4e";

function makeRepo({ missingProject = "", failure = "", timeout = "" } = {}) {
  const repoRoot = fs.mkdtempSync(path.join(os.tmpdir(), "rts01-registered-projects-"));
  const projects = {};
  for (const projectId of REGISTERED_PROJECT_IDS) {
    const root = path.join("projects", projectId);
    const absoluteRoot = path.join(repoRoot, root);
    if (projectId !== missingProject) {
      fs.mkdirSync(absoluteRoot, { recursive: true });
      fs.writeFileSync(path.join(absoluteRoot, "index.html"), "<!doctype html><title>fixture</title>\n", "utf8");
    }
    projects[projectId] = {
      root,
      automation_mode: "bounded_write",
      policy_scope: projectId,
      allowed_write_tools: [],
      allowed_test_tools: ["runtime.run_test"],
      tests: [{ runner: "static_smoke", target: "index.html", timeoutSec: 30 }],
    };
  }

  if (failure) {
    const root = path.join(repoRoot, projects[failure].root, "tests");
    fs.mkdirSync(root, { recursive: true });
    fs.writeFileSync(path.join(root, "failure.test.js"), "import test from 'node:test'; test('fails', () => { throw new Error('fixture failure'); });\n", "utf8");
    projects[failure].tests = [{ runner: "node_test", target: "tests", timeoutSec: 30 }];
  }
  if (timeout) {
    const root = path.join(repoRoot, projects[timeout].root, "tests");
    fs.mkdirSync(root, { recursive: true });
    fs.writeFileSync(path.join(root, "timeout.test.js"), "setTimeout(() => {}, 20000);\n", "utf8");
    projects[timeout].tests = [{ runner: "node_test", target: "tests", timeoutSec: 1 }];
  }

  const profilesPath = path.join(repoRoot, "runtime", "test-profiles.json");
  fs.mkdirSync(path.dirname(profilesPath), { recursive: true });
  fs.writeFileSync(profilesPath, JSON.stringify({
    schema_version: 1,
    policy: { arbitrary_shell: false, max_timeout_seconds: 120 },
    projects,
  }, null, 2) + "\n", "utf8");
  return { repoRoot, profilesPath, outputPath: path.join(repoRoot, "evidence.json") };
}

function cleanup(repoRoot) {
  fs.rmSync(repoRoot, { recursive: true, force: true });
}

test("collects passing evidence for all eight fixed registered projects", () => {
  const fixture = makeRepo();
  try {
    const packet = collectRegisteredProjectsEvidence({
      ...fixture,
      sourceSnapshotSha,
    });
    assert.equal(packet.status, "pass");
    assert.deepEqual(packet.registered_projects.map((item) => item.project_id), REGISTERED_PROJECT_IDS);
    assert.ok(packet.registered_projects.every((item) => item.root_exists && item.status === "pass"));
    assert.ok(packet.registered_projects.every((item) => item.source_scope === "runtime/test-profiles.json" && item.profile_sha256.length === 64));
    assert.equal(new Set(packet.registered_projects.map((item) => item.profile_sha256)).size, REGISTERED_PROJECT_IDS.length);
    assert.equal(packet.arbitrary_commands, false);
    assert.equal(packet.writes_forbidden, true);
    assert.deepEqual(JSON.parse(fs.readFileSync(fixture.outputPath, "utf8")), packet);
  } finally {
    cleanup(fixture.repoRoot);
  }
});

test("missing registered project root fails closed", () => {
  const missingProject = "white-studio-games";
  const fixture = makeRepo({ missingProject });
  try {
    const packet = collectRegisteredProjectsEvidence({ ...fixture, sourceSnapshotSha });
    const project = packet.registered_projects.find((item) => item.project_id === missingProject);
    assert.equal(packet.status, "fail");
    assert.equal(project.root_exists, false);
    assert.ok(packet.reasons.includes("registered_project_root_missing"));
  } finally {
    cleanup(fixture.repoRoot);
  }
});

test("a fixed profile test failure keeps the registered-project packet failed", () => {
  const failedProject = "white-studio-web";
  const fixture = makeRepo({ failure: failedProject });
  try {
    const packet = collectRegisteredProjectsEvidence({ ...fixture, sourceSnapshotSha });
    const project = packet.registered_projects.find((item) => item.project_id === failedProject);
    assert.equal(packet.status, "fail");
    assert.equal(project.fixed_tests[0].status, "fail");
    assert.ok(packet.reasons.includes("registered_project_fixed_test_failed"));
  } finally {
    cleanup(fixture.repoRoot);
  }
});

test("a fixed profile test timeout is recorded as a failure", () => {
  const timeoutProject = "partner-site-demo";
  const fixture = makeRepo({ timeout: timeoutProject });
  try {
    const packet = collectRegisteredProjectsEvidence({ ...fixture, sourceSnapshotSha });
    const project = packet.registered_projects.find((item) => item.project_id === timeoutProject);
    assert.equal(packet.status, "fail");
    assert.equal(project.fixed_tests[0].status, "timeout");
    assert.equal(project.fixed_tests[0].timed_out, true);
    assert.ok(packet.reasons.includes("registered_project_fixed_test_failed"));
  } finally {
    cleanup(fixture.repoRoot);
  }
});

test("collector forwards a fixed python_script profile to runtime.run_test", () => {
  const fixture = makeRepo();
  try {
    const desktop = REGISTERED_PROJECT_IDS[0];
    const desktopRoot = path.join(fixture.repoRoot, "projects", desktop, "tests");
    fs.mkdirSync(desktopRoot, { recursive: true });
    fs.writeFileSync(path.join(desktopRoot, "profile_check.py"), "print('profile-check')\n", "utf8");
    const profiles = JSON.parse(fs.readFileSync(fixture.profilesPath, "utf8"));
    profiles.projects[desktop].tests = [{ runner: "python_script", target: "tests/profile_check.py", timeoutSec: 30 }];
    fs.writeFileSync(fixture.profilesPath, JSON.stringify(profiles, null, 2) + "\n", "utf8");

    const calls = [];
    const packet = collectRegisteredProjectsEvidence({
      ...fixture,
      sourceSnapshotSha,
      workspaceFactory: () => ({
        runTest(args) {
          calls.push(args);
          return { ok: true, timed_out: false, exit_code: 0 };
        },
      }),
    });
    const project = packet.registered_projects.find((item) => item.project_id === desktop);
    assert.equal(project.status, "pass");
    assert.equal(project.fixed_tests[0].runner, "python_script");
    assert.deepEqual(calls[0], {
      runner: "python_script",
      target: "tests/profile_check.py",
      projectDir: path.join("projects", desktop),
      timeoutSec: 30,
    });
  } finally {
    cleanup(fixture.repoRoot);
  }
});

test("a registered project without fixed profile tests fails closed", () => {
  const fixture = makeRepo();
  try {
    const projectId = "partner-site-demo";
    const profiles = JSON.parse(fs.readFileSync(fixture.profilesPath, "utf8"));
    profiles.projects[projectId].tests = [];
    fs.writeFileSync(fixture.profilesPath, JSON.stringify(profiles, null, 2) + "\n", "utf8");

    const packet = collectRegisteredProjectsEvidence({ ...fixture, sourceSnapshotSha });
    const project = packet.registered_projects.find((item) => item.project_id === projectId);
    assert.equal(packet.status, "fail");
    assert.equal(project.fixed_tests[0].error_code, "registered_project_fixed_tests_missing");
    assert.ok(packet.reasons.includes("registered_project_fixed_test_missing"));
  } finally {
    cleanup(fixture.repoRoot);
  }
});
