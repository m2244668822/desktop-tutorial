#!/usr/bin/env python3
"""Validate the local n8n training workflow before importing it."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
ALLOWED_HEALTH_URL = "http://127.0.0.1:5001/health/ready"
REQUIRED_NODES = {
    "Manual Trigger",
    "Read Trevor readiness",
    "Health gate",
    "Run fixed training evaluator",
    "Sanitize result",
}


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _urls(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"url", "uri"} and isinstance(child, str):
                yield child
            yield from _urls(child)
    elif isinstance(value, list):
        for child in value:
            yield from _urls(child)


def validate_workflow(path: str | Path) -> list[str]:
    target = Path(path).expanduser()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["invalid_json"]
    if not isinstance(payload, dict):
        return ["workflow_not_object"]

    errors: list[str] = []
    if not isinstance(payload.get("id"), str) or not str(payload.get("id", "")).strip():
        errors.append("workflow_id_required")
    if payload.get("active") is not False:
        errors.append("workflow_must_be_inactive")
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return ["nodes_required"]
    node_names = {str(node.get("name", "")) for node in nodes if isinstance(node, dict)}
    for required in sorted(REQUIRED_NODES - node_names):
        errors.append(f"required_node_missing:{required}")
    trigger_types = [str(node.get("type", "")) for node in nodes if isinstance(node, dict) and str(node.get("type", "")).endswith("Trigger")]
    if trigger_types.count("n8n-nodes-base.manualTrigger") != 1:
        errors.append("manual_trigger_required")
    if any(trigger in {"n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.webhook"} for trigger in trigger_types):
        errors.append("schedule_or_webhook_trigger_forbidden")
    if any(isinstance(item, dict) and "credentials" in item for item in _walk(payload)):
        errors.append("credentials_forbidden")

    for url in _urls(payload):
        if url != ALLOWED_HEALTH_URL:
            errors.append("external_url_forbidden")
            break

    execute_nodes = [node for node in nodes if isinstance(node, dict) and node.get("type") == "n8n-nodes-base.executeCommand"]
    if len(execute_nodes) != 1:
        errors.append("execute_command_required")
    else:
        command = str((execute_nodes[0].get("parameters") or {}).get("command", ""))
        if any(token in command for token in ("{{", "$json", "$input")):
            errors.append("dynamic_command_forbidden")
        if "n8n_training_evaluation.py" not in command:
            errors.append("fixed_wrapper_command_required")
        if any(operator in command for operator in ("&&", "||", ";", "|")):
            errors.append("command_operator_forbidden")

    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path, required=True)
    args = parser.parse_args()
    errors = validate_workflow(args.workflow)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"ok": True, "workflow": str(args.workflow)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
