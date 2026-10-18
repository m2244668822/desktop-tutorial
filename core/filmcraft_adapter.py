"""Bounded stdio FilmCraft MCP adapter.

The adapter defaults to the disposable built-in demo. A real project requires
an explicit project path and a caller-provided fingerprint; no implicit
`current` target is accepted.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any


class FilmCraftMcpError(RuntimeError):
    pass


class JsonlMcpProcess:
    def __init__(self, executable: str, *, demo: bool = True, project: str | None = None, timeout: float = 15.0):
        self.executable = executable
        self.demo = demo
        self.project = project
        self.timeout = timeout
        self._process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self._unmatched: dict[int, dict[str, Any]] = {}
        self._response_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._next_id = 1

    def start(self) -> dict[str, Any]:
        args = [self.executable]
        if self.demo:
            args.append("--demo")
        if self.project:
            args.extend(["--project", self.project])
        args.append("mcp")
        self._process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "white-studio-orchestrator", "version": "1.0"},
            },
        )
        self.notify("notifications/initialized", {})
        return result

    def _read_loop(self) -> None:
        assert self._process and self._process.stdout
        for line in self._process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and "id" in message:
                self._responses.put(message)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise FilmCraftMcpError("server_not_started")
        self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n")
        self._process.stdin.flush()

    def _response_for(self, request_id: int) -> dict[str, Any]:
        with self._response_lock:
            existing = self._unmatched.pop(request_id, None)
        if existing is not None:
            return existing

        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FilmCraftMcpError("timeout")
            try:
                response = self._responses.get(timeout=remaining)
            except queue.Empty as exc:
                raise FilmCraftMcpError("timeout") from exc
            response_id = response.get("id")
            if response_id == request_id:
                return response
            if isinstance(response_id, int):
                with self._response_lock:
                    self._unmatched[response_id] = response

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._process or not self._process.stdin:
            raise FilmCraftMcpError("server_not_started")
        request_id = self._next_id
        self._next_id += 1
        self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n")
        self._process.stdin.flush()
        response = self._response_for(request_id)
        if response.get("error"):
            raise FilmCraftMcpError(str(response["error"]))
        return response.get("result") or {}

    def close(self) -> None:
        process, self._process = self._process, None
        if not process:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()


class FilmCraftMcpAdapter:
    def __init__(self, client: JsonlMcpProcess, *, project_id: str, project_fingerprint: str):
        if not project_id or project_id == "current":
            raise ValueError("project_id_required")
        if not project_fingerprint:
            raise ValueError("project_fingerprint_required")
        self.client = client
        self.project_id = project_id
        self.project_fingerprint = project_fingerprint
        self._tools: dict[str, dict[str, Any]] | None = None
        self.last_call_context: dict[str, str] | None = None

    def call_with_context(
        self,
        *,
        context: dict[str, Any],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep White Studio operation identity at the adapter boundary.

        FilmCraft's own MCP wire protocol receives only FilmCraft arguments.
        White Studio identity is retained locally for orchestration and audit;
        it is never forwarded as an unknown upstream parameter.
        """
        required = ("task_id", "run_id", "operation_id", "idempotency_key")
        if any(not str(context.get(key, "")).strip() for key in required):
            raise FilmCraftMcpError("schema_invalid:identity")
        self.last_call_context = {key: str(context[key]) for key in required}
        return self.call(tool_name, arguments)

    def tools_list(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._tools is not None and not refresh:
            return {"tools": list(self._tools.values())}
        result = self.client.request("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            raise FilmCraftMcpError("tools_list_invalid")
        normalized: dict[str, dict[str, Any]] = {}
        for tool in tools:
            if (
                not isinstance(tool, dict)
                or not isinstance(tool.get("name"), str)
                or not tool["name"]
                or not isinstance(tool.get("inputSchema"), dict)
                or tool["name"] in normalized
            ):
                raise FilmCraftMcpError("tools_list_invalid")
            normalized[tool["name"]] = tool
        self._tools = normalized
        return result

    @staticmethod
    def _wire_tool_name(tool_name: str) -> str:
        if tool_name in {"markers_add", "edit_undo"}:
            return "command_run"
        if tool_name == "state_snapshot":
            return "doc_inspect"
        return tool_name

    def _ensure_tool_available(self, tool_name: str) -> None:
        tools = self.tools_list().get("tools", []) if self._tools is None else list(self._tools.values())
        names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
        wire_name = self._wire_tool_name(tool_name)
        if wire_name not in names:
            raise FilmCraftMcpError(f"tool_unavailable:{wire_name}")

    @staticmethod
    def _json_type_matches(value: Any, expected: Any) -> bool:
        expected_types = expected if isinstance(expected, list) else [expected]
        for type_name in expected_types:
            if type_name == "object" and isinstance(value, dict):
                return True
            if type_name == "array" and isinstance(value, list):
                return True
            if type_name == "string" and isinstance(value, str):
                return True
            if type_name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
            if type_name == "integer" and isinstance(value, int) and not isinstance(value, bool):
                return True
            if type_name == "boolean" and isinstance(value, bool):
                return True
            if type_name == "null" and value is None:
                return True
        return False

    def _validate_wire_arguments(self, wire_name: str, arguments: dict[str, Any], schema: dict[str, Any]) -> None:
        if not isinstance(arguments, dict) or schema.get("type", "object") != "object":
            raise FilmCraftMcpError(f"schema_invalid:{wire_name}")
        required = schema.get("required", [])
        if not isinstance(required, list) or any(
            not isinstance(item, str) or item not in arguments for item in required
        ):
            raise FilmCraftMcpError(f"schema_invalid:{wire_name}")
        properties = schema.get("properties", {})
        if properties is not None and not isinstance(properties, dict):
            raise FilmCraftMcpError(f"schema_invalid:{wire_name}")
        if isinstance(properties, dict):
            for name, descriptor in properties.items():
                if name not in arguments or not isinstance(descriptor, dict):
                    continue
                if "type" in descriptor and not self._json_type_matches(arguments[name], descriptor["type"]):
                    raise FilmCraftMcpError(f"schema_invalid:{wire_name}.{name}")
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            if any(name not in properties for name in arguments):
                raise FilmCraftMcpError(f"schema_invalid:{wire_name}")

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "state_snapshot":
            return self.state_snapshot()
        elif tool_name == "edit_undo":
            tool_name, arguments = "command_run", {"id": "edit.undo", "params": arguments}
        elif tool_name == "markers_add":
            tool_name, arguments = "command_run", {"id": "markers.add", "params": arguments}
        self._ensure_tool_available(tool_name)
        descriptor = self._tools[tool_name]
        self._validate_wire_arguments(tool_name, arguments, descriptor["inputSchema"])
        result = self.client.request("tools/call", {"name": tool_name, "arguments": arguments})
        content = result.get("content") if isinstance(result, dict) else None
        if isinstance(content, list) and content and isinstance(content[0], dict) and content[0].get("text"):
            try:
                return json.loads(content[0]["text"])
            except json.JSONDecodeError:
                return result
        return result

    def state_snapshot(self) -> dict[str, Any]:
        return self.canonical_state(self.raw_state_snapshot())

    def raw_state_snapshot(self) -> dict[str, Any]:
        return self.call("doc_inspect", {})

    @staticmethod
    def canonical_state(snapshot: dict[str, Any]) -> dict[str, Any]:
        """Remove runtime-only fields while retaining all edit state.

        FilmCraft increments revision and keeps the project dirty after an
        undo. Those fields describe history bookkeeping, not the resulting
        project content. Raw snapshots remain available for audit evidence.
        """
        value = deepcopy(snapshot)
        project = value.get("project")
        if isinstance(project, dict):
            project.pop("revision", None)
            project.pop("dirty", None)
        return value

    def project_inspect(self) -> dict[str, Any]:
        return self.call("project_inspect", {})

    def sequence_inspect(self) -> dict[str, Any]:
        return self.call("sequence_inspect", {})

    def marker_list(self) -> dict[str, Any]:
        return self.sequence_inspect()

    def markers_add(self, *, seconds: float, name: str) -> dict[str, Any]:
        return self.call("command_run", {"id": "markers.add", "params": {"seconds": seconds, "name": name}})

    def edit_undo(self) -> dict[str, Any]:
        return self.call("command_run", {"id": "edit.undo", "params": {}})


def demo_executable() -> str:
    return os.environ.get("FILMCRAFT_CLI", r"C:\Program Files\FilmCraft\filmcraft-cli.exe")


def executable_available(path: str | None = None) -> bool:
    return Path(path or demo_executable()).is_file()
