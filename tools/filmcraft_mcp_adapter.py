#!/usr/bin/env python3
"""Bounded stdio MCP adapter for the installed FilmCraft CLI.

This process is a local bridge, not a replacement FilmCraft runtime. It starts
the CLI's own MCP process, exposes the small White Studio contract, and keeps
real-project writes disabled unless the caller explicitly supplies the
real-write flag and an immutable project target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from core.filmcraft_adapter import FilmCraftMcpAdapter, FilmCraftMcpError, JsonlMcpProcess, demo_executable


PROTOCOL_VERSION = "2024-11-05"
SERVER_VERSION = "0.1.0"
READ_ONLY_TOOLS = {"project_inspect", "sequence_inspect", "marker_list", "state_snapshot", "doc_inspect", "state_compare"}
WRITE_TOOLS = {"markers_add", "command_run", "edit_undo"}


def _schema(*, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        result["required"] = required
    return result


def contract_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "project_inspect",
            "description": "Read the FilmCraft project tree.",
            "inputSchema": _schema(),
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
        },
        {
            "name": "sequence_inspect",
            "description": "Read the active FilmCraft sequence.",
            "inputSchema": _schema(),
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
        },
        {
            "name": "marker_list",
            "description": "Read the active sequence markers.",
            "inputSchema": _schema(),
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
        },
        {
            "name": "doc_inspect",
            "description": "Read the complete FilmCraft document snapshot.",
            "inputSchema": _schema(),
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
        },
        {
            "name": "state_snapshot",
            "description": "Read a canonical state snapshot for S0/S3 comparison.",
            "inputSchema": _schema(),
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
        },
        {
            "name": "state_compare",
            "description": "Compare two supplied canonical snapshots locally.",
            "inputSchema": _schema(
                properties={"before": {"type": "object"}, "after": {"type": "object"}},
                required=["before", "after"],
            ),
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
        },
        {
            "name": "markers_add",
            "description": "Add one marker. Disposable or explicitly authorized real-project write only.",
            "inputSchema": _schema(
                properties={"seconds": {"type": "number"}, "name": {"type": "string"}},
                required=["seconds", "name"],
            ),
            "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
        },
        {
            "name": "command_run",
            "description": "Run one FilmCraft command. Write policy is enforced by this adapter.",
            "inputSchema": _schema(
                properties={"id": {"type": "string"}, "params": {"type": "object"}},
                required=["id"],
            ),
            "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
        },
        {
            "name": "edit_undo",
            "description": "Undo the last edit through FilmCraft command_run.",
            "inputSchema": _schema(),
            "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
        },
    ]


def _json_text(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, sort_keys=True)}]}


def _state_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class FilmCraftAdapterServer:
    def __init__(self, args: argparse.Namespace):
        if args.demo and args.project:
            raise ValueError("demo_project_conflict")
        if not args.demo and (not args.project or not args.project_id or args.project_id == "current"):
            raise ValueError("real_project_requires_explicit_target")
        if not args.demo and not args.project_fingerprint:
            raise ValueError("real_project_fingerprint_required")
        self.args = args
        self.client = JsonlMcpProcess(
            args.executable or demo_executable(),
            demo=bool(args.demo),
            project=args.project,
        )
        self.adapter: FilmCraftMcpAdapter | None = None
        self.initialized = False
        # This is a process-local safety cache. Durable task identity belongs to
        # the orchestrator, but the adapter must still prevent an immediate
        # duplicate write while one stdio session is alive.
        self._idempotency_cache: dict[str, dict[str, Any]] = {}

    def initialize(self) -> dict[str, Any]:
        child = self.client.start()
        self.adapter = FilmCraftMcpAdapter(
            self.client,
            project_id="demo" if self.args.demo else self.args.project_id,
            project_fingerprint="sha256:filmcraft-demo" if self.args.demo else self.args.project_fingerprint,
        )
        self.adapter.tools_list()
        self.initialized = True
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "filmcraft-adapter", "version": SERVER_VERSION},
            "instructions": "Local FilmCraft bridge. Real-project writes require explicit launch authorization.",
            "upstream": child.get("serverInfo", {}),
        }

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _context_from(params: dict[str, Any], arguments: dict[str, Any]) -> dict[str, str]:
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        supplied = meta.get("whiteStudio") if isinstance(meta.get("whiteStudio"), dict) else None
        if supplied is None and isinstance(arguments.get("_context"), dict):
            supplied = arguments.get("_context")
        context = supplied or {}
        return {str(key): str(value).strip() for key, value in context.items() if value is not None}

    def _validate_context(self, name: str, context: dict[str, str]) -> None:
        required = ("task_id", "run_id", "operation_id", "idempotency_key", "capability")
        missing = [key for key in required if not context.get(key)]
        if missing:
            raise FilmCraftMcpError("schema_invalid:identity:" + ",".join(missing))
        if name in WRITE_TOOLS:
            capability = context.get("capability")
            expected = "real_write" if not self.args.demo else "disposable_write"
            if capability != expected:
                raise FilmCraftMcpError("authorization_required:" + expected)
            if context.get("project_id") != ("demo" if self.args.demo else self.args.project_id):
                raise FilmCraftMcpError("project_required:project_id_mismatch")
            if context.get("project_fingerprint") != (
                "sha256:filmcraft-demo" if self.args.demo else self.args.project_fingerprint
            ):
                raise FilmCraftMcpError("project_fingerprint_mismatch")
        elif context.get("capability") != "read":
            raise FilmCraftMcpError("authorization_required:read")

    @staticmethod
    def _operation_fingerprint(name: str, arguments: dict[str, Any]) -> str:
        safe = {key: value for key, value in arguments.items() if key != "_context"}
        encoded = json.dumps({"tool": name, "arguments": safe}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _mutation_result(
        self,
        *,
        name: str,
        context: dict[str, str],
        before: dict[str, Any],
        result: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        envelope = deepcopy(result)
        envelope.update(
            {
                "success": True,
                "task_id": context["task_id"],
                "run_id": context["run_id"],
                "operation_id": context["operation_id"],
                "idempotency_key": context["idempotency_key"],
                "project_id": self.args.project_id if not self.args.demo else "demo",
                "before_state_hash": _state_hash(before),
                "after_state_hash": _state_hash(after),
                "undo_available": name in {"markers_add", "command_run"}
                and result.get("undone") is None,
                "source": "filmcraft-adapter",
                "runtime_version": SERVER_VERSION,
            }
        )
        return envelope

    def call_tool(self, name: str, arguments: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
        if not self.initialized or self.adapter is None:
            raise FilmCraftMcpError("server_not_initialized")
        if name not in READ_ONLY_TOOLS | WRITE_TOOLS:
            raise FilmCraftMcpError(f"tool_unavailable:{name}")
        self._validate_context(name, context)
        idempotency_key = context["idempotency_key"]
        fingerprint = self._operation_fingerprint(name, arguments)
        cached = self._idempotency_cache.get(idempotency_key)
        if cached is not None:
            if cached["fingerprint"] != fingerprint:
                raise FilmCraftMcpError("idempotency_conflict")
            return deepcopy(cached["result"])
        if name in WRITE_TOOLS and not self.args.demo and not self.args.allow_real_write:
            raise FilmCraftMcpError("authorization_required:real_project_write")
        if name == "state_compare":
            before = arguments.get("before")
            after = arguments.get("after")
            if not isinstance(before, dict) or not isinstance(after, dict):
                raise FilmCraftMcpError("schema_invalid:state_compare")
            result = {"equal": before == after, "before_state_hash": _state_hash(before), "after_state_hash": _state_hash(after)}
            self._idempotency_cache[idempotency_key] = {"fingerprint": fingerprint, "result": deepcopy(result)}
            return result
        if name == "state_snapshot":
            return self.adapter.state_snapshot()
        if name == "marker_list":
            return self.adapter.marker_list()
        if name == "markers_add":
            if (
                not isinstance(arguments.get("seconds"), (int, float))
                or isinstance(arguments.get("seconds"), bool)
                or not isinstance(arguments.get("name"), str)
                or not arguments.get("name", "").strip()
            ):
                raise FilmCraftMcpError("schema_invalid:markers_add")
            before = self.adapter.state_snapshot()
            result = self.adapter.markers_add(seconds=float(arguments["seconds"]), name=str(arguments["name"]))
            after = self.adapter.state_snapshot()
            envelope = self._mutation_result(name=name, context=context, before=before, result=result, after=after)
            self._idempotency_cache[idempotency_key] = {"fingerprint": fingerprint, "result": deepcopy(envelope)}
            return envelope
        if name == "edit_undo":
            before = self.adapter.state_snapshot()
            result = self.adapter.edit_undo()
            after = self.adapter.state_snapshot()
            envelope = self._mutation_result(name=name, context=context, before=before, result=result, after=after)
            envelope["undo_available"] = False
            self._idempotency_cache[idempotency_key] = {"fingerprint": fingerprint, "result": deepcopy(envelope)}
            return envelope
        before = self.adapter.state_snapshot() if name == "command_run" else None
        wire_arguments = {key: value for key, value in arguments.items() if key != "_context"}
        result = self.adapter.call(name, wire_arguments)
        if name == "command_run":
            after = self.adapter.state_snapshot()
            envelope = self._mutation_result(name=name, context=context, before=before or {}, result=result, after=after)
            self._idempotency_cache[idempotency_key] = {"fingerprint": fingerprint, "result": deepcopy(envelope)}
            return envelope
        return result


def _error_response(request_id: Any, message: str, code: int = -32602) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(args: argparse.Namespace) -> int:
    server = FilmCraftAdapterServer(args)
    try:
        for raw in sys.stdin:
            try:
                request = json.loads(raw)
                if not isinstance(request, dict):
                    continue
                request_id = request.get("id")
                method = request.get("method")
                params = request.get("params") if isinstance(request.get("params"), dict) else {}
                if method == "notifications/initialized":
                    continue
                if method == "initialize":
                    result = server.initialize()
                elif method == "tools/list":
                    if not server.initialized:
                        raise FilmCraftMcpError("server_not_initialized")
                    result = {"tools": contract_tools()}
                elif method == "tools/call":
                    name = params.get("name")
                    arguments = params.get("arguments", {})
                    if not isinstance(name, str) or not isinstance(arguments, dict):
                        raise FilmCraftMcpError("schema_invalid:tools_call")
                    context = server._context_from(params, arguments)
                    result = _json_text(server.call_tool(name, arguments, context))
                else:
                    raise FilmCraftMcpError(f"method_not_found:{method}")
                if request_id is not None:
                    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}, ensure_ascii=False) + "\n")
                    sys.stdout.flush()
            except Exception as exc:
                if request_id is not None:
                    sys.stdout.write(json.dumps(_error_response(request_id, str(exc)), ensure_ascii=False) + "\n")
                    sys.stdout.flush()
    finally:
        server.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Use FilmCraft's disposable demo project.")
    parser.add_argument("--project", help="Explicit real project path; never defaults to current.")
    parser.add_argument("--project-id", default="", help="Stable project identity for real-project mode.")
    parser.add_argument("--project-fingerprint", default="", help="Precomputed project fingerprint for real-project mode.")
    parser.add_argument("--allow-real-write", action="store_true", help="Explicitly authorize writes to the supplied real project.")
    parser.add_argument("--executable", default="", help="FilmCraft CLI path; defaults to FILMCRAFT_CLI or the installed path.")
    args = parser.parse_args()
    try:
        return serve(args)
    except Exception as exc:
        print(f"filmcraft_adapter_start_failed:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
