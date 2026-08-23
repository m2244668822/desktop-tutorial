#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal command layer dispatcher for agent platform entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping


CommandHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
BASE_DIR = Path(__file__).resolve().parent.parent
_DEBUG_LOG_PATH = BASE_DIR / ".cursor" / "debug-baa814.log"


def _agent_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    payload = {
        "sessionId": "baa814",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(__import__("time").time() * 1000),
    }
    try:
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def dispatch_command(
    request: Mapping[str, Any], handlers: Mapping[str, CommandHandler]
) -> dict[str, Any]:
    """Dispatch a command request to a named handler.

    Request shape:
    {
      "command": "chat|status|workflow|...",
      "payload": {...},
      "meta": {...}
    }
    """
    supported_commands = sorted(handlers.keys())
    run_id = str(request.get("meta", {}).get("debugRunId", "run-unknown")) if isinstance(request.get("meta", {}), dict) else "run-unknown"
    command = str(request.get("command", "")).strip().lower()
    payload = _coerce_dict(request.get("payload"))
    meta = _coerce_dict(request.get("meta"))
    _agent_log(
        run_id,
        "H1",
        "core/command_layer.py:dispatch_command",
        "dispatch entry",
        {"command": command, "payload_keys": sorted(payload.keys()), "meta_keys": sorted(meta.keys())},
    )

    if not command:
        _agent_log(
            run_id,
            "H1",
            "core/command_layer.py:dispatch_command",
            "command missing",
            {"supported_commands": supported_commands},
        )
        return {
            "ok": False,
            "error": "command_required",
            "supported_commands": supported_commands,
        }

    handler = handlers.get(command)
    if handler is None:
        _agent_log(
            run_id,
            "H1",
            "core/command_layer.py:dispatch_command",
            "unsupported command",
            {"command": command, "supported_commands": supported_commands},
        )
        return {
            "ok": False,
            "command": command,
            "error": "unsupported_command",
            "supported_commands": supported_commands,
        }

    try:
        result = handler(payload, meta)
    except Exception as exc:  # pragma: no cover - safety net at integration boundary
        _agent_log(
            run_id,
            "H5",
            "core/command_layer.py:dispatch_command",
            "handler exception",
            {"command": command, "error": str(exc)},
        )
        return {
            "ok": False,
            "command": command,
            "error": "command_failed",
            "detail": str(exc),
        }

    _agent_log(
        run_id,
        "H5",
        "core/command_layer.py:dispatch_command",
        "dispatch success",
        {"command": command, "result_keys": sorted(result.keys()) if isinstance(result, dict) else []},
    )
    return {"ok": True, "command": command, "result": result}
