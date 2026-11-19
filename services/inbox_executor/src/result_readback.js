import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { taskIdFromText, topLevelSections } from "./inbox.js";

function resultFields(section) {
  const fields = new Map();
  for (const line of section.text.slice(section.heading.length).trimStart().split(/\r?\n/)) {
    if (!line.startsWith("- ")) break;
    const completion = line.match(/^- (?:時間|completed_at)[:：][ \t]*(\S+)[ \t]*$/);
    if (completion) {
      if (fields.has("completed_at")) throw new Error("result_field_duplicated:completed_at");
      fields.set("completed_at", completion[1]);
      continue;
    }
    const field = line.match(/^- (task_id|trace_id|run_id|remote_task_revision)[ \t]*[:：][ \t]*\x60([^ \t\x60]+)\x60[ \t]*$/);
    if (!field) continue;
    if (fields.has(field[1])) throw new Error("result_field_duplicated:" + field[1]);
    fields.set(field[1], field[2]);
  }
  return fields;
}

export function readTerminalResult(text, expectedTask, side) {
  const frontmatter = text.match(/^\uFEFF?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/)?.[1];
  const status = frontmatter?.match(/^status:[ \t]*(done|blocked)[ \t]*\r?$/m)?.[1];
  if (!status) throw new Error(side + "_result_status_not_terminal");
  if (taskIdFromText(text) !== expectedTask) {
    throw new Error(side + "_result_task_id_mismatch");
  }

  const results = topLevelSections(text)
    .filter(({ heading }) => /^## Result(?:$|[（(])/.test(heading))
    .map(resultFields)
    .filter((fields) => fields.get("task_id") === expectedTask);
  if (results.length === 0) throw new Error(side + "_result_task_id_mismatch");
  if (results.length > 1) throw new Error(side + "_result_ambiguous");
  const trace = results[0].get("trace_id");
  if (!trace || !/^[A-Za-z0-9_.:-]+$/.test(trace)) {
    throw new Error(side + "_result_trace_id_missing");
  }
  return { status, trace, fields: results[0] };
}

export function verifyResultReadback(localText, remoteText, expectedTask) {
  if (!expectedTask || expectedTask === "unknown") throw new Error("result_task_id_required");
  const local = readTerminalResult(localText, expectedTask, "local");
  const remote = readTerminalResult(remoteText, expectedTask, "remote");
  if (local.status !== remote.status) throw new Error("remote_result_status_mismatch");
  if (local.trace !== remote.trace) throw new Error("remote_result_trace_id_mismatch");
  return { task_id: expectedTask, trace_id: remote.trace, status: remote.status };
}

export function readCommittedTask(commit, taskPath, cwd) {
  if (!/^[0-9a-f]{40}(?:[0-9a-f]{24})?$/.test(commit) || !taskPath) {
    throw new Error("result_readback_invalid_git_input");
  }
  try {
    return execFileSync("git", ["show", commit + ":" + taskPath.replace(/\\/g, "/"), "--"], {
      encoding: "utf8",
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 30000,
    });
  } catch {
    throw new Error("result_readback_git_show_failed");
  }
}

export function readGitRevision(cwd, ref) {
  return execFileSync("git", ["rev-parse", "--verify", ref], {
    cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 10000,
  }).trim();
}

export function commitOnRemoteRef(cwd, commit, refs) {
  if (!/^[0-9a-f]{40}(?:[0-9a-f]{24})?$/.test(commit)) return false;
  const containing = execFileSync("git", ["for-each-ref", "--contains=" + commit, "--format=%(refname)", ...refs], {
    cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 10000,
  }).trim().split(/\r?\n/);
  return refs.some((ref) => containing.includes(ref));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [localCommit, remoteCommit, taskPath, taskId] = process.argv.slice(2);
  try {
    const local = readCommittedTask(localCommit, taskPath);
    const remote = readCommittedTask(remoteCommit, taskPath);
    console.log(JSON.stringify(verifyResultReadback(local, remote, taskId)));
  } catch (error) {
    console.log(error.message);
    process.exitCode = 1;
  }
}
