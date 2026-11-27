import crypto from "node:crypto";

export function createOperationId() {
  return crypto.randomUUID();
}

export function operationResultFields({ operationId, taskId }) {
  if (typeof operationId !== "string" || !operationId.trim()) {
    throw new TypeError("operation_id_required");
  }
  if (typeof taskId !== "string" || !taskId.trim()) {
    throw new TypeError("task_id_required");
  }
  return [`- operation_id：\`${operationId}\``, `- task_id：\`${taskId}\``];
}

export function buildTerminalResult({ operationId, taskId, status, identityMarkdown, details = [] }) {
  if (!new Set(["done", "blocked"]).has(status)) {
    throw new TypeError("terminal_result_status_invalid");
  }
  return [
    ...operationResultFields({ operationId, taskId }),
    `- 結果：${status}`,
    identityMarkdown,
    ...details,
  ].join("\n");
}
