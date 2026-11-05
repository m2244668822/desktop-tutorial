#!/usr/bin/env node
import fs from "node:fs";
import { processConversationEvent } from "./conversation_event.js";

async function readInput() {
  const file = process.argv[2];
  if (file) return fs.readFileSync(file, "utf8");

  let body = "";
  for await (const chunk of process.stdin) body += chunk;
  return body;
}

try {
  const raw = await readInput();
  const input = JSON.parse(raw);
  const result = processConversationEvent(input);
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
} catch (error) {
  const code = error?.code || "conversation_event_error";
  process.stderr.write(
    JSON.stringify({
      ok: false,
      code,
      message: String(error?.message || error),
    }) + "\n"
  );
  process.exit(2);
}
