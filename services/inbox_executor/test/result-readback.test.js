import assert from "node:assert/strict";
import test from "node:test";
import { verifyResultReadback } from "../src/result_readback.js";

const taskId = "rts01-readback-fixture";
const traceId = "2484cb1e-d26a-4000-80a2-a0e4590c452a";
const otherTrace = "98a66ce4-80a2-4cb1-8607-407b6cc6b130";

function result({ status = "done", resultTask = taskId, trace = traceId, history = "" } = {}) {
  return [
    "---",
    "status: " + status,
    "---",
    "",
    "## 現在這一份契約",
    "",
    "task_id       " + taskId,
    "",
    history,
    "## Result（inbox-daemon 回寫）",
    "",
    "- task_id：\x60" + resultTask + "\x60",
    trace ? "- trace_id：\x60" + trace + "\x60" : "",
    "- 結果：" + status,
    "",
  ].join("\n");
}

test("matches the same task and trace across LF and CRLF Results", () => {
  assert.deepEqual(verifyResultReadback(result(), result().replace(/\n/g, "\r\n"), taskId), {
    task_id: taskId,
    trace_id: traceId,
    status: "done",
  });
});

test("rejects a different remote trace even when the local trace appears in history", () => {
  const history = "## History\n\n- trace_id：\x60" + traceId + "\x60\n";
  assert.throws(
    () => verifyResultReadback(result(), result({ trace: otherTrace, history }), taskId),
    /remote_result_trace_id_mismatch/,
  );
});

test("rejects a missing active trace even when a fenced Result example has it", () => {
  const history = "~~~markdown\n## Result\n- task_id：\x60" + taskId +
    "\x60\n- trace_id：\x60" + traceId + "\x60\n~~~\n";
  assert.throws(
    () => verifyResultReadback(result({ trace: "", history }), result(), taskId),
    /local_result_trace_id_missing/,
  );
  assert.throws(
    () => verifyResultReadback(result(), result({ trace: "", history }), taskId),
    /remote_result_trace_id_missing/,
  );
});

test("rejects a different Result task and a different terminal status", () => {
  assert.throws(
    () => verifyResultReadback(result(), result({ resultTask: "other-task" }), taskId),
    /remote_result_task_id_mismatch/,
  );
  assert.throws(
    () => verifyResultReadback(result(), result({ status: "blocked" }), taskId),
    /remote_result_status_mismatch/,
  );
});

test("preserves blocked as a terminal outcome after an exact readback", () => {
  const blocked = result({ status: "blocked" });
  assert.equal(verifyResultReadback(blocked, blocked, taskId).status, "blocked");
});

test("accepts the same trace under the agentic Result heading", () => {
  const agentic = result().replace("inbox-daemon", "codex-executor");
  assert.equal(verifyResultReadback(agentic, agentic, taskId).trace_id, traceId);
});
