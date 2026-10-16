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

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._process or not self._process.stdin:
            raise FilmCraftMcpError("server_not_started")
        request_id = self._next_id
        self._next_id += 1
        self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n")
        self._process.stdin.flush()
        try:
            response = self._responses.get(timeout=self.timeout)
        except queue.Empty as exc:
            raise FilmCraftMcpError("timeout") from exc
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

    def tools_list(self) -> dict[str, Any]:
        return self.client.request("tools/list", {})

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "state_snapshot":
            return self.state_snapshot()
        elif tool_name == "edit_undo":
            tool_name, arguments = "command_run", {"id": "edit.undo", "params": arguments}
        elif tool_name == "markers_add":
            tool_name, arguments = "command_run", {"id": "markers.add", "params": arguments}
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
