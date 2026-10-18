#!/usr/bin/env python3
"""Run the disposable FilmCraft MCP S0/S1/S2/S3 orchestrator smoke test."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from core.durable_task_store import DurableTaskStore
from core.filmcraft_adapter import FilmCraftMcpAdapter, JsonlMcpProcess, demo_executable
from core.mcp_orchestrator import Orchestrator
from core.orchestrator_types import OperationContext


def main() -> int:
    client = JsonlMcpProcess(demo_executable(), demo=True)
    try:
        initialize = client.start()
        adapter = FilmCraftMcpAdapter(
            client,
            project_id="demo",
            project_fingerprint="sha256:filmcraft-demo",
        )
        with tempfile.TemporaryDirectory(prefix="white-studio-orchestrator-") as root:
            result = Orchestrator(DurableTaskStore(root)).run_mutation(
                context=OperationContext.create("filmcraft-orchestrator-smoke"),
                client=adapter,
                tool_name="markers_add",
                arguments={"seconds": 1.0, "name": "orchestrator-smoke"},
                project_id="demo",
                project_fingerprint="sha256:filmcraft-demo",
                undo_tool="edit_undo",
                result_validator=lambda before, after: before != after,
            )
        payload = {
            "server": initialize.get("serverInfo"),
            "status": result["record"]["status"],
            "validation_status": result["record"]["validation_status"],
            "state_compare": result["result"]["state_compare"],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if payload["status"] == "completed" and payload["validation_status"] == "passed" else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
