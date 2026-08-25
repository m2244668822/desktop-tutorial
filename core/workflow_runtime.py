#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
import contextlib
import io
import inspect
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.autonomy_claim import ClaimLostError
from core.data_paths import ProjectPaths, is_link_like, resolve_data_root
from core.interprocess_lock import exclusive_file_lock

try:
    from core.llm_cns import (
        describe_key_state as _describe_key_state_cns,
        is_placeholder_value as _is_placeholder_value_cns,
        llm_snapshot,
        load_combined_env as _load_combined_env_cns,
    )
except Exception:
    _describe_key_state_cns = None
    _is_placeholder_value_cns = None
    llm_snapshot = None
    _load_combined_env_cns = None

try:
    from tools.local_memory_api import LocalMemoryAPI
except Exception:
    LocalMemoryAPI = None

try:
    from tools.build_knowledge_ingestion import build_pipeline
except Exception:
    build_pipeline = None


CancellationCheck = Callable[[], None]
ToolHandler = Callable[..., dict[str, Any]]
ToolVerifier = Callable[[dict[str, Any]], tuple[bool, str]]


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    verifier: ToolVerifier
    max_retries: int = 1


@dataclass
class TaskStepState:
    tool_name: str
    description: str
    status: str = "pending"
    attempts: int = 0
    verified: bool = False
    verification_notes: str = ""
    input_payload: dict[str, Any] = field(default_factory=dict)
    output_payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_class: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    attempt_logs: list[dict[str, Any]] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _check_cancel(cancel_check: CancellationCheck | None) -> None:
    if cancel_check is not None:
        cancel_check()


def _supports_cancel_check(handler: ToolHandler) -> bool:
    try:
        parameters = inspect.signature(handler).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        or (
            parameter.name == "cancel_check"
            and parameter.kind
            in {
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }
        )
        for parameter in parameters
    )


def _invoke_tool_handler(
    handler: ToolHandler,
    workspace: Path,
    payload: dict[str, Any],
    cancel_check: CancellationCheck | None,
) -> dict[str, Any]:
    if cancel_check is not None and _supports_cancel_check(handler):
        return handler(workspace, payload, cancel_check=cancel_check)
    return handler(workspace, payload)


def _write_text_with_cancellation(
    path: Path,
    content: str,
    *,
    cancel_check: CancellationCheck | None,
) -> None:
    _check_cancel(cancel_check)
    lock_path = path.parent / ".trevor-write.lock"
    with exclusive_file_lock(lock_path):
        _check_cancel(cancel_check)
        encoded = content.encode("utf-8")
        previous = path.read_bytes() if path.is_file() else None
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        installed = False
        try:
            temporary.write_bytes(encoded)
            _check_cancel(cancel_check)
            os.replace(temporary, path)
            installed = True
            try:
                _check_cancel(cancel_check)
            except Exception:
                try:
                    if path.is_file() and path.read_bytes() == encoded:
                        if previous is None:
                            path.unlink(missing_ok=True)
                        else:
                            restore = path.with_name(
                                f".{path.name}.{uuid.uuid4().hex}.restore"
                            )
                            restore.write_bytes(previous)
                            os.replace(restore, path)
                finally:
                    raise
        finally:
            if not installed:
                temporary.unlink(missing_ok=True)


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        value = value.strip()
        if value and not value.startswith(("'", '"')) and "#" in value:
            value = value.split("#", 1)[0].rstrip()
        data[key.strip()] = value.strip('"').strip("'")
    return data


def _is_placeholder_value(value: str) -> bool:
    if _is_placeholder_value_cns is not None:
        return _is_placeholder_value_cns(value)
    text = str(value or "").strip().lower()
    return (
        not text
        or "placeholder" in text
        or "example" in text
        or text.startswith("your_")
        or text.endswith("_here")
        or text in {"none", "null", "changeme", "your_api_key"}
    )


def _describe_key_state(key: str) -> str:
    if _describe_key_state_cns is not None:
        return _describe_key_state_cns(key)
    clean = str(key or "").strip()
    if not clean:
        return "missing"
    if _is_placeholder_value(clean):
        return "placeholder"
    return f"configured(len={len(clean)})"


def _load_combined_env(workspace: Path) -> tuple[dict[str, str], Path]:
    if _load_combined_env_cns is not None:
        return _load_combined_env_cns(workspace)
    
    paths = ProjectPaths(workspace)
    primary = paths.env_main
    candidates = paths.env_candidates
    
    merged: dict[str, str] = {}
    alias_map = {"GOOLE_API_KEY": "GOOGLE_API_KEY"}
    for path in candidates:
        file_data = _load_env(path)
        for key, value in file_data.items():
            key = alias_map.get(key, key)
            current = merged.get(key, "")
            if key not in merged:
                merged[key] = value
                continue
            if _is_placeholder_value(current) and not _is_placeholder_value(value):
                merged[key] = value
            elif not current and value:
                merged[key] = value
    return merged, primary


def _git_summary(workspace: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            check=False,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        lines = [line for line in out.splitlines() if line.strip()]
        if proc.returncode == 0:
            return "\n".join(lines[:8]) if lines else "clean"

        merged = "\n".join([part for part in (out, err) if part]).lower()
        if any(
            marker in merged
            for marker in (
                "invalid sha1 pointer",
                "object file",
                "object corrupt",
                "missing blob",
                "invalid reflog entry",
                "fatal: bad object",
            )
        ):
            return "degraded: git metadata corrupt"
        if "not a git repository" in merged:
            return "degraded: not a git repository"
        return f"degraded: git status unavailable (rc={proc.returncode})"
    except Exception:
        return "degraded: git command unavailable"


def _tool_tiered_storage_health(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    env, _ = _load_combined_env(workspace)
    paths = ProjectPaths(workspace)
    
    configured_ssd = payload.get("ssd_root") or os.environ.get("SSD_ROOT") or env.get("SSD_ROOT")
    ssd_path = (
        Path(configured_ssd).expanduser()
        if isinstance(configured_ssd, str) and configured_ssd.strip()
        else None
    )
    data_root = paths.data
    data_path = workspace / "data"
    ssd_mounted = bool(ssd_path and ssd_path.exists())
    hdd_mounted = (workspace / "data_hdd_storage").exists()
    return {
        "ssd_mounted": ssd_mounted,
        "hdd_mounted": hdd_mounted,
        "data_symlink_ok": is_link_like(data_path) or data_path.is_dir() or data_root.is_dir(),
        "data_root": str(data_root),
        "performance_mode": "ssd_turbo" if ssd_mounted else ("hdd_ready" if hdd_mounted else "degraded_hdd"),
        "timestamp": _now_iso(),
    }


def _verify_storage_health(output: dict[str, Any]) -> tuple[bool, str]:
    ok = bool(output.get("ssd_mounted")) or bool(output.get("hdd_mounted"))
    return ok, "storage ready" if ok else "storage missing"


def _tool_workspace_status(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspace": str(workspace),
        "vscode_workspace_exists": (workspace / ".vscode").exists(),
        "git_summary": _git_summary(workspace),
        "timestamp": _now_iso(),
    }


def _verify_workspace_status(output: dict[str, Any]) -> tuple[bool, str]:
    return bool(output.get("workspace")), "workspace inspected"


def _tool_api_config(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if llm_snapshot is not None:
        return llm_snapshot(workspace)
    env, env_path = _load_combined_env(workspace)
    key = env.get("NVAPI_API_KEY", env.get("OPENAI_API_KEY", ""))
    return {
        "env_path": str(env_path),
        "key_source": "NVAPI_API_KEY" if env.get("NVAPI_API_KEY") else "OPENAI_API_KEY",
        "key_state": _describe_key_state(key),
        "base_url": str(env.get("OPENAI_BASE_URL", "")).strip(),
        "model": str(env.get("OPENAI_MODEL", "")).strip() or "missing",
        "open_source_model": str(
            env.get("OPEN_SOURCE_CHAT_MODEL", env.get("OLLAMA_MODEL", ""))
        ).strip()
        or "missing",
        "providers": [],
    }


def _verify_api_config(output: dict[str, Any]) -> tuple[bool, str]:
    ok = bool(output.get("base_url")) and str(output.get("model", "")) != "missing"
    return ok, "api config ready" if ok else "api config incomplete"


def _tool_knowledge_hub_manifest(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    paths = ProjectPaths(workspace)
    manifest_path = paths.knowledge_manifest
    manifest = _load_json(manifest_path, {})
    hub_status: dict[str, Any] = {}
    try:
        from core.knowledge_hub import KnowledgeHub

        hub_status = KnowledgeHub(workspace).status()
    except Exception as exc:
        hub_status = {"ok": False, "error": str(exc)}

    chatgpt_database_path = str(
        hub_status.get("chatgpt_database_path")
        or manifest.get("chatgpt_database_path", "")
    )
    chatgpt_database_ready = bool(
        hub_status.get("chatgpt_database_ready")
        or manifest.get("chatgpt_database_ready", False)
    )
    return {
        "manifest_path": str(manifest_path),
        "exists": manifest_path.exists(),
        "sources": manifest.get("sources", {}),
        "ready": bool(
            chatgpt_database_ready
            and (hub_status.get("sqlite_ready") or hub_status.get("faiss_ready"))
        ),
        "chatgpt_database_ready": chatgpt_database_ready,
        "chatgpt_database_path": chatgpt_database_path,
        "sqlite_ready": bool(hub_status.get("sqlite_ready")),
        "faiss_ready": bool(hub_status.get("faiss_ready")),
        "total_items": int(hub_status.get("total_items", 0) or 0),
        "hub_status": hub_status,
    }


def _verify_knowledge_hub(output: dict[str, Any]) -> tuple[bool, str]:
    if output.get("exists"):
        return True, "knowledge hub manifest found"
    return True, "knowledge hub manifest missing but non-blocking"


def _tool_open_source_catalog(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    paths = ProjectPaths(workspace)
    catalog_path = paths.catalog_json
    catalog = _load_json(catalog_path, [])
    query = str(payload.get("query", "")).lower()
    tokens = re.findall(r"[a-z0-9_\\-]+|[\u4e00-\u9fff]{2,6}", query)
    matches: list[dict[str, Any]] = []
    for item in catalog:
        haystack = " ".join(
            str(item.get(key, "")).lower() for key in ("name", "kind", "focus", "why", "license")
        )
        if any(token in haystack for token in tokens if token):
            matches.append(item)
    if not matches:
        matches = [item for item in catalog if item.get("kind") == "framework"][:5]
    return {"catalog_path": str(catalog_path), "count": len(catalog), "matches": matches[:5]}


def _verify_catalog(output: dict[str, Any]) -> tuple[bool, str]:
    return bool(output.get("catalog_path")), "catalog checked"


def _tool_workspace_search(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    if not query:
        return {"query": query, "matches": [], "error": "empty_query"}
    limit = int(payload.get("limit", 8) or 8)
    try:
        proc = subprocess.run(
            [
                "rg",
                "--line-number",
                "--hidden",
                "--glob",
                "!.git",
                "--max-count",
                str(max(1, limit)),
                query,
                str(workspace),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
            check=False,
        )
        matches = [line for line in (proc.stdout or "").splitlines() if line.strip()]
        return {"query": query, "matches": matches[:limit], "returncode": proc.returncode}
    except Exception as exc:
        return {"query": query, "matches": [], "error": str(exc)}


def _verify_workspace_search(output: dict[str, Any]) -> tuple[bool, str]:
    if output.get("error") == "empty_query":
        return False, "workspace search query missing"
    return True, "workspace search done"


def _tool_aeg_keyword_graph(
    workspace: Path,
    payload: dict[str, Any],
    *,
    cancel_check: CancellationCheck | None = None,
) -> dict[str, Any]:
    """Build AEG keyword graph from local memory, ChatGPT DB, Git and n8n context."""
    _check_cancel(cancel_check)
    limit = max(20, int(payload.get("limit", 80) or 80))
    token_re = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}|[\u4e00-\u9fff]{2,6}")
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "from",
        "this",
        "workflow",
        "agent",
        "debug",
        "fix",
    }

    def is_garbled(token: str) -> bool:
        raw = str(token or "").strip()
        if not raw:
            return True
        if any(0xE000 <= ord(ch) <= 0xF8FF for ch in raw):
            return True
        return "??" in raw or "�" in raw

    paths = ProjectPaths(workspace)
    text_items: list[dict[str, str]] = []
    source_files_seen: set[str] = set()

    def add_text(source: str, text: str, source_id: str = "", meta: dict[str, Any] | None = None) -> None:
        _check_cancel(cancel_check)
        clean = " ".join(str(text or "").split()).strip()
        if len(clean) < 8:
            return
        text_items.append(
            {
                "source": source,
                "source_id": source_id,
                "text": clean[:5000],
                "meta": json.dumps(meta or {}, ensure_ascii=False),
            }
        )

    conversation_candidates = [
        paths.data / "agent_memories" / "conversations.json",
        workspace / "data_hdd_storage" / "agent_memories" / "conversations.json",
    ]
    for conv_path in conversation_candidates:
        _check_cancel(cancel_check)
        if not conv_path.exists():
            continue
        data = _load_json(conv_path, {})
        if not isinstance(data, dict):
            continue
        source_files_seen.add(str(conv_path))
        for conv in data.values():
            _check_cancel(cancel_check)
            if not isinstance(conv, dict):
                continue
            for msg in conv.get("messages", []):
                _check_cancel(cancel_check)
                add_text(
                    "agent_memory",
                    str(msg.get("user", "")),
                    str(conv.get("id", "")),
                    {"agent_name": conv.get("agent_name", "")},
                )
                add_text(
                    "agent_memory",
                    str(msg.get("assistant", "")),
                    str(conv.get("id", "")),
                    {"agent_name": conv.get("agent_name", "")},
                )

    legacy = paths.llama_data / "conversations.json"
    _check_cancel(cancel_check)
    if legacy.exists():
        rows = _load_json(legacy, [])
        if isinstance(rows, list):
            source_files_seen.add(str(legacy))
            for row in rows:
                _check_cancel(cancel_check)
                if not isinstance(row, dict):
                    continue
                add_text("gpt_history", str(row.get("prompt", "")), str(row.get("id", "")))
                add_text("gpt_history", str(row.get("response", "")), str(row.get("id", "")))

    if LocalMemoryAPI is not None:
        try:
            _check_cancel(cancel_check)
            # LocalMemoryAPI(chatgpt_limit=None) is the canonical loader for the
            # exported ChatGPT database. Redirect its progress output so the
            # scheduler does not bring back the noisy console problem we are fixing.
            with contextlib.redirect_stdout(io.StringIO()):
                api = LocalMemoryAPI(str(workspace), chatgpt_limit=None)
                conversations = api.get_all_conversations(refresh=True)
            _check_cancel(cancel_check)
            for conv in conversations:
                _check_cancel(cancel_check)
                if not isinstance(conv, dict) or conv.get("source") != "chatgpt_database":
                    continue
                conv_id = str(conv.get("id", ""))
                title = str(conv.get("title", ""))
                meta = dict(conv.get("metadata", {}) or {})
                meta["title"] = title
                add_text(
                    "chatgpt_database",
                    "\n".join(part for part in (title, str(conv.get("user_input", ""))) if part),
                    f"{conv_id}:user",
                    meta,
                )
                add_text(
                    "chatgpt_database",
                    "\n".join(part for part in (title, str(conv.get("assistant_response", ""))) if part),
                    f"{conv_id}:assistant",
                    meta,
                )
            source_files_seen.add("LocalMemoryAPI(chatgpt_limit=None)")
        except ClaimLostError:
            raise
        except Exception:
            pass

    _check_cancel(cancel_check)
    git_context = _git_summary(workspace)
    add_text("git_context", git_context, "git:status")

    n8n_status = "n8n optional scheduler"
    try:
        _check_cancel(cancel_check)
        proc = subprocess.run(
            ["bash", "-lc", "lsof -nP -iTCP:5678 -sTCP:LISTEN | head -n 2"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        n8n_status = "n8n_runtime listening" if (proc.stdout or "").strip() else "n8n_runtime degraded optional"
    except ClaimLostError:
        raise
    except Exception:
        n8n_status = "n8n_runtime unknown optional"
    add_text("n8n_runtime", n8n_status, "n8n:5678")

    keyword_counter: Counter[str] = Counter()
    edge_counter: defaultdict[tuple[str, str], int] = defaultdict(int)
    skipped_garbled = 0
    readable_tokens = 0
    source_breakdown: Counter[str] = Counter(item["source"] for item in text_items)

    for item in text_items:
        _check_cancel(cancel_check)
        text_row = item["text"]
        tokens = [t.lower() for t in token_re.findall(text_row or "") if len(t) >= 2]
        clean_tokens = []
        for token in tokens:
            if token in stop_words:
                continue
            if is_garbled(token):
                skipped_garbled += 1
                continue
            clean_tokens.append(token)
            readable_tokens += 1

        uniq = list(dict.fromkeys(clean_tokens))[:12]
        for token in uniq:
            keyword_counter[token] += 1
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                a, b = sorted((uniq[i], uniq[j]))
                edge_counter[(a, b)] += 1

    top_keywords = [{"keyword": k, "count": c} for k, c in keyword_counter.most_common(limit)]
    top_edges = [
        {"a": a, "b": b, "weight": w, "relation": "shared_keyword"}
        for (a, b), w in sorted(edge_counter.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]
    denominator = max(1, readable_tokens + skipped_garbled)
    readable_ratio = round(readable_tokens / denominator, 4)

    out_dir = paths.data / "knowledge_hub"
    _check_cancel(cancel_check)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "aeg_keyword_graph.json"
    out_payload = {
        "generated_at": _now_iso(),
        "sources_seen": len(source_files_seen),
        "source_breakdown": dict(source_breakdown),
        "text_items": len(text_items),
        "keywords_count": len(top_keywords),
        "edges_count": len(top_edges),
        "skipped_garbled_tokens": skipped_garbled,
        "readable_ratio": readable_ratio,
        "metadata": {
            "git_summary": git_context,
            "n8n_runtime": n8n_status,
            "runtime_report": "data/knowledge_hub/reports/AEG_SHARED_REPORT_LATEST.md",
            "canonical_report": "reports/AEG_SHARED_REPORT.md",
        },
        "keywords": top_keywords,
        "edges": top_edges,
    }
    _write_text_with_cancellation(
        out_path,
        json.dumps(out_payload, ensure_ascii=False, indent=2) + "\n",
        cancel_check=cancel_check,
    )
    return {
        "path": str(out_path),
        "sources_seen": len(source_files_seen),
        "source_breakdown": dict(source_breakdown),
        "text_items": len(text_items),
        "keywords_count": len(top_keywords),
        "edges_count": len(top_edges),
        "skipped_garbled_tokens": skipped_garbled,
        "readable_ratio": readable_ratio,
        "top_keywords": top_keywords[:15],
    }


def _verify_aeg_keyword_graph(output: dict[str, Any]) -> tuple[bool, str]:
    ok = bool(output.get("path")) and int(output.get("keywords_count", 0) or 0) > 0
    return ok, "aeg graph built" if ok else "aeg graph empty"


def _tool_long_term_memory(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    top_k = int(payload.get("top_k", 5) or 5)
    try:
        from core.knowledge_hub import KnowledgeHub

        hub = KnowledgeHub(workspace)
        status = hub.status()
        if status.get("sqlite_ready") or status.get("faiss_ready"):
            result = hub.search(query, top_k=top_k) if query else {"matches": []}
            matches = result.get("matches", []) if isinstance(result, dict) else []
            return {
                "query": query,
                "matches": matches,
                "status": {
                    "available": True,
                    "sqlite_ready": bool(status.get("sqlite_ready")),
                    "faiss_ready": bool(status.get("faiss_ready")),
                    "total_items": int(status.get("total_items", 0) or 0),
                    "sqlite_path": status.get("sqlite_path", ""),
                    "faiss_path": status.get("faiss_path", ""),
                    "meta_path": status.get("meta_path", ""),
                },
            }
    except Exception:
        pass

    if LocalMemoryAPI is None:
        return {"query": query, "matches": [], "status": {"available": False}}
    try:
        api = LocalMemoryAPI(str(workspace))
        if hasattr(api, "search_long_term_memory"):
            result = api.search_long_term_memory(query=query, top_k=top_k)
            if isinstance(result, dict):
                return result
        return {"query": query, "matches": [], "status": {"available": True}}
    except Exception as exc:
        return {"query": query, "matches": [], "status": {"available": False, "error": str(exc)}}


def _verify_long_term_memory(output: dict[str, Any]) -> tuple[bool, str]:
    return True, "long-term memory queried"


def _tool_context_layers(workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    memory = _tool_long_term_memory(workspace, {"query": query, "top_k": 6})
    matches = list(memory.get("matches", [])) if isinstance(memory, dict) else []
    layers = {
        "l0": matches[:2],
        "l1": matches[2:4],
        "l2": matches[4:6],
    }
    return {"query": query, "layers": layers}


def _verify_context_layers(output: dict[str, Any]) -> tuple[bool, str]:
    return True, "context layers assembled"


def _tool_build_knowledge_ingestion(
    workspace: Path,
    payload: dict[str, Any],
    *,
    cancel_check: CancellationCheck | None = None,
) -> dict[str, Any]:
    _check_cancel(cancel_check)
    if build_pipeline is None:
        return {"ok": False, "error": "build_pipeline_unavailable"}
    try:
        result = build_pipeline(workspace, cancel_check=cancel_check)
        _check_cancel(cancel_check)
        return {"ok": True, "result": result}
    except ClaimLostError:
        raise
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _verify_build_knowledge_ingestion(output: dict[str, Any]) -> tuple[bool, str]:
    if output.get("ok"):
        return True, "knowledge ingestion built"
    return False, str(output.get("error", "build_knowledge_ingestion_failed"))


def _tool_write_knowledge_note(
    workspace: Path,
    payload: dict[str, Any],
    *,
    cancel_check: CancellationCheck | None = None,
) -> dict[str, Any]:
    _check_cancel(cancel_check)
    paths = ProjectPaths(workspace)
    title = str(payload.get("title", "")).strip() or "workflow-note"
    summary = str(payload.get("summary", "")).strip()
    route = str(payload.get("route", "")).strip()
    task_id = str(payload.get("task_id", "")).strip()
    source_input = str(payload.get("source_input", "")).strip()
    if not summary:
        return {"path": "", "written": False, "error": "empty_summary"}

    note_dir = paths.data / "knowledge_hub" / "notes" / datetime.now().strftime("%Y%m%d")
    fallback_dir = paths.logs / "knowledge_hub" / "notes" / datetime.now().strftime("%Y%m%d")
    used_fallback = False
    try:
        _check_cancel(cancel_check)
        note_dir.mkdir(parents=True, exist_ok=True)
    except ClaimLostError:
        raise
    except Exception:
        _check_cancel(cancel_check)
        fallback_dir.mkdir(parents=True, exist_ok=True)
        note_dir = fallback_dir
        used_fallback = True
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title).strip("-").lower() or "note"
    note_path = note_dir / f"{datetime.now().strftime('%H%M%S')}-{slug}.md"
    content = "\n".join(
        [
            f"# {title}",
            "",
            f"- created_at: {_now_iso()}",
            f"- route: {route or 'unknown'}",
            f"- task_id: {task_id or 'N/A'}",
            "",
            "## Summary",
            summary,
            "",
            "## Source Input",
            source_input or "N/A",
            "",
        ]
    )
    _write_text_with_cancellation(
        note_path,
        content + "\n",
        cancel_check=cancel_check,
    )
    return {"path": str(note_path), "written": True, "fallback": used_fallback}


def _verify_write_knowledge_note(output: dict[str, Any]) -> tuple[bool, str]:
    ok = bool(output.get("written")) and bool(output.get("path"))
    return ok, "knowledge note written" if ok else str(output.get("error", "write_failed"))


def _tool_save_workspace_report(
    workspace: Path,
    payload: dict[str, Any],
    *,
    cancel_check: CancellationCheck | None = None,
) -> dict[str, Any]:
    _check_cancel(cancel_check)
    paths = ProjectPaths(workspace)
    title = str(payload.get("title", "")).strip() or "workflow-report"
    summary = str(payload.get("summary", "")).strip()
    route = str(payload.get("route", "")).strip()
    task_id = str(payload.get("task_id", "")).strip()
    report_dir = paths.reports / "workflow_runs"
    _check_cancel(cancel_check)
    report_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title).strip("-").lower() or "report"
    report_path = report_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-{slug}.md"
    lines = [
        f"# {title}",
        "",
        f"- created_at: {_now_iso()}",
        f"- route: {route or 'unknown'}",
        f"- task_id: {task_id or 'N/A'}",
        "",
        "## Summary",
        summary or "N/A",
        "",
    ]
    _write_text_with_cancellation(
        report_path,
        "\n".join(lines),
        cancel_check=cancel_check,
    )
    return {"path": str(report_path), "written": True}


def _verify_save_workspace_report(output: dict[str, Any]) -> tuple[bool, str]:
    ok = bool(output.get("written")) and bool(output.get("path"))
    return ok, "workspace report saved" if ok else "report save failed"


def build_tool_registry() -> dict[str, ToolSpec]:
    return {
        "tiered_storage_health": ToolSpec(
            name="tiered_storage_health",
            description="Check storage status for shared workspace",
            handler=_tool_tiered_storage_health,
            verifier=_verify_storage_health,
        ),
        "workspace_status": ToolSpec(
            name="workspace_status",
            description="Check git/workspace baseline",
            handler=_tool_workspace_status,
            verifier=_verify_workspace_status,
        ),
        "api_config": ToolSpec(
            name="api_config",
            description="Inspect provider config",
            handler=_tool_api_config,
            verifier=_verify_api_config,
        ),
        "knowledge_hub_manifest": ToolSpec(
            name="knowledge_hub_manifest",
            description="Read knowledge hub manifest",
            handler=_tool_knowledge_hub_manifest,
            verifier=_verify_knowledge_hub,
        ),
        "open_source_catalog": ToolSpec(
            name="open_source_catalog",
            description="Search local open-source catalog",
            handler=_tool_open_source_catalog,
            verifier=_verify_catalog,
        ),
        "workspace_search": ToolSpec(
            name="workspace_search",
            description="Search workspace text",
            handler=_tool_workspace_search,
            verifier=_verify_workspace_search,
        ),
        "aeg_keyword_graph": ToolSpec(
            name="aeg_keyword_graph",
            description="Build AEG keyword relation graph from local GPT/agent chats",
            handler=_tool_aeg_keyword_graph,
            verifier=_verify_aeg_keyword_graph,
        ),
        "long_term_memory": ToolSpec(
            name="long_term_memory",
            description="Search local long-term memory",
            handler=_tool_long_term_memory,
            verifier=_verify_long_term_memory,
        ),
        "context_layers": ToolSpec(
            name="context_layers",
            description="Prepare L0/L1/L2 context layers",
            handler=_tool_context_layers,
            verifier=_verify_context_layers,
        ),
        "build_knowledge_ingestion": ToolSpec(
            name="build_knowledge_ingestion",
            description="Build knowledge ingestion artifacts",
            handler=_tool_build_knowledge_ingestion,
            verifier=_verify_build_knowledge_ingestion,
        ),
        "write_knowledge_note": ToolSpec(
            name="write_knowledge_note",
            description="Write knowledge note markdown",
            handler=_tool_write_knowledge_note,
            verifier=_verify_write_knowledge_note,
        ),
        "save_workspace_report": ToolSpec(
            name="save_workspace_report",
            description="Write workspace run report",
            handler=_tool_save_workspace_report,
            verifier=_verify_save_workspace_report,
        ),
    }


def _classify_error(error: str) -> str:
    text = str(error or "").lower()
    if any(token in text for token in ("timeout", "timed out")):
        return "timeout"
    if any(token in text for token in ("not found", "missing", "empty_")):
        return "config_or_input_error"
    if any(token in text for token in ("verify", "failed", "degraded")):
        return "verification_failed"
    return "runtime_error"


def _execute_steps(
    workspace: Path,
    route: str,
    user_input: str,
    task_id: str,
    steps: list[tuple[str, dict[str, Any]]],
    parent_task_id: str = "",
    rerun_from: str = "",
    cancel_check: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = build_tool_registry()
    tool_outputs: dict[str, Any] = {}
    step_states: list[TaskStepState] = []
    retries_used = 0
    retried_tools: list[str] = []

    for tool_name, payload in steps:
        if cancel_check is not None:
            cancel_check()
        spec = registry.get(tool_name)
        row = TaskStepState(
            tool_name=tool_name,
            description=spec.description if spec else "unknown tool",
            input_payload=dict(payload or {}),
            started_at=_now_iso(),
        )
        if spec is None:
            row.status = "failed"
            row.error = "tool_not_registered"
            row.error_class = "config_or_input_error"
            row.finished_at = _now_iso()
            step_states.append(row)
            continue

        attempts = max(1, int(spec.max_retries or 1))
        for attempt in range(1, attempts + 1):
            if cancel_check is not None:
                cancel_check()
            row.attempts = attempt
            attempt_started = datetime.now()
            try:
                output = _invoke_tool_handler(
                    spec.handler,
                    workspace,
                    dict(payload or {}),
                    cancel_check,
                )
                if cancel_check is not None:
                    cancel_check()
                ok, note = spec.verifier(output)
                row.output_payload = output
                row.verified = bool(ok)
                row.verification_notes = str(note)
                row.attempt_logs.append({"attempt": attempt, "ok": bool(ok), "note": str(note)})
                if ok:
                    row.status = "success"
                    break
                row.status = "failed"
                row.error = str(note)
                row.error_class = _classify_error(note)
            except ClaimLostError:
                raise
            except Exception as exc:
                row.status = "failed"
                row.error = str(exc)
                row.error_class = _classify_error(str(exc))
                row.attempt_logs.append({"attempt": attempt, "ok": False, "note": str(exc)})
            finally:
                row.duration_ms += int((datetime.now() - attempt_started).total_seconds() * 1000)
            if row.status == "failed" and attempt < attempts:
                retries_used += 1
                retried_tools.append(tool_name)
        row.finished_at = _now_iso()
        tool_outputs[tool_name] = row.output_payload
        step_states.append(row)

    completed_steps = sum(1 for item in step_states if item.status == "success")
    failed_steps = sum(1 for item in step_states if item.status == "failed")
    overall_status = "success" if completed_steps and not failed_steps else ("partial" if completed_steps else "failed")
    task_state = {
        "task_id": task_id,
        "trace_id": f"trace-{uuid.uuid4().hex[:16]}",
        "parent_task_id": parent_task_id,
        "rerun_from": rerun_from,
        "route": route,
        "user_input": user_input,
        "overall_status": overall_status,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "retries_used": retries_used,
        "steps": [asdict(item) for item in step_states],
        "tool_registry": {
            name: {"description": spec.description, "max_retries": spec.max_retries}
            for name, spec in registry.items()
        },
        "created_at": _now_iso(),
    }
    return task_state, tool_outputs


def _write_task_log(
    workspace: Path,
    user_input: str,
    task_state: dict[str, Any],
    *,
    cancel_check: CancellationCheck | None = None,
) -> str:
    _check_cancel(cancel_check)
    paths = ProjectPaths(workspace)
    log_dir = paths.logs / "workflow_runs"
    try:
        _check_cancel(cancel_check)
        log_dir.mkdir(parents=True, exist_ok=True)
    except ClaimLostError:
        raise
    except Exception:
        _check_cancel(cancel_check)
        log_dir = workspace / "logs" / "workflow_runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        task_state["log_path_fallback"] = True
    log_path = log_dir / f"{task_state.get('task_id', 'wf-unknown')}.json"
    _write_text_with_cancellation(
        log_path,
        json.dumps(
            {
                "created_at": _now_iso(),
                "trace_id": task_state.get("trace_id", ""),
                "user_input": user_input,
                "task_state": task_state,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        cancel_check=cancel_check,
    )
    task_state["log_path"] = str(log_path)
    return str(log_path)


def choose_task_steps(route: str, user_input: str) -> list[tuple[str, dict[str, Any]]]:
    text = str(user_input or "")
    route_text = str(route or "").strip().lower()
    steps: list[tuple[str, dict[str, Any]]] = [
        ("workspace_status", {}),
        ("api_config", {}),
        ("tiered_storage_health", {}),
        ("knowledge_hub_manifest", {}),
        ("context_layers", {"query": text, "top_k": 6}),
        ("long_term_memory", {"query": text, "top_k": 8}),
    ]
    if route_text in {"research", "prophet"} or any(token in text.lower() for token in ("research", "study", "analyze")):
        steps.extend(
            [
                ("aeg_keyword_graph", {"limit": 80}),
                ("open_source_catalog", {"query": text}),
                ("workspace_search", {"query": text, "limit": 10}),
            ]
        )
    elif route_text in {"engineering", "security"} or any(token in text.lower() for token in ("fix", "debug", "repair", "bug")):
        steps.append(("workspace_search", {"query": text or "todo", "limit": 12}))
        steps.append(("open_source_catalog", {"query": "langgraph workflow"}))
    else:
        steps.append(("workspace_search", {"query": text or "workflow", "limit": 8}))
    return steps


def build_action_steps(
    route: str, user_input: str, tool_outputs: dict[str, Any], task_id: str
) -> list[tuple[str, dict[str, Any]]]:
    ws = tool_outputs.get("workspace_status", {}) if isinstance(tool_outputs, dict) else {}
    summary_lines = [
        f"route={route}",
        f"git={ws.get('git_summary', 'unknown')}",
        f"input={user_input[:200]}",
    ]
    summary = " | ".join(summary_lines)
    return [
        (
            "write_knowledge_note",
            {
                "title": f"workflow-{route or 'run'}",
                "summary": summary,
                "route": route,
                "task_id": task_id,
                "source_input": user_input,
            },
        ),
        (
            "save_workspace_report",
            {
                "title": f"workflow-report-{route or 'run'}",
                "summary": summary,
                "route": route,
                "task_id": task_id,
            },
        ),
    ]


def run_task_plan(
    workspace: str | Path,
    route: str,
    user_input: str,
    *,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if cancel_check is not None:
        cancel_check()
    workspace_path = Path(workspace).expanduser().resolve()
    task_id = f"wf-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    steps = choose_task_steps(route, user_input)
    preview_state, preview_outputs = _execute_steps(
        workspace=workspace_path,
        route=route,
        user_input=user_input,
        task_id=task_id,
        steps=steps,
        cancel_check=cancel_check,
    )

    memory_write_allowed = (
        str(preview_state.get("overall_status", "")).lower() == "success"
        and int(preview_state.get("failed_steps", 0) or 0) == 0
        and int(preview_state.get("completed_steps", 0) or 0) > 0
    )

    if memory_write_allowed:
        if cancel_check is not None:
            cancel_check()
        action_steps = build_action_steps(route, user_input, preview_outputs, task_id)
        action_state, action_outputs = _execute_steps(
            workspace=workspace_path,
            route=route,
            user_input=user_input,
            task_id=task_id,
            steps=action_steps,
            parent_task_id=task_id,
            cancel_check=cancel_check,
        )
        merged_outputs = dict(preview_outputs)
        merged_outputs.update(action_outputs)
        merged_steps = list(preview_state.get("steps", [])) + list(action_state.get("steps", []))
        completed_steps = sum(1 for step in merged_steps if step.get("status") == "success")
        failed_steps = sum(1 for step in merged_steps if step.get("status") == "failed")
        overall_status = "success" if completed_steps and not failed_steps else ("partial" if completed_steps else "failed")
        preview_state.update(
            {
                "overall_status": overall_status,
                "completed_steps": completed_steps,
                "failed_steps": failed_steps,
                "steps": merged_steps,
                "memory_write_allowed": True,
                "memory_write_block_reason": "",
                "action_write_executed": True,
                "memory_layers": "L0/L1/L2",
            }
        )
        tool_outputs = merged_outputs
    else:
        preview_state["memory_write_allowed"] = False
        preview_state["memory_write_block_reason"] = "preview_not_success"
        preview_state["action_write_executed"] = False
        preview_state["memory_layers"] = "L0/L1/L2"
        tool_outputs = preview_outputs

    if cancel_check is not None:
        cancel_check()
    _write_task_log(
        workspace_path,
        user_input,
        preview_state,
        cancel_check=cancel_check,
    )
    return {"task_state": preview_state, "tool_outputs": tool_outputs}


def rerun_task_step(
    workspace: str | Path,
    task_id: str,
    tool_name: str = "",
    step_index: int | None = None,
    include_downstream: bool = True,
) -> dict[str, Any]:
    workspace_path = Path(workspace).expanduser().resolve()
    data_root = resolve_data_root(workspace_path)
    source_log = data_root / "workflow_runs" / f"{task_id}.json"
    if not source_log.exists():
        source_log = workspace_path / "logs" / "workflow_runs" / f"{task_id}.json"
    payload = _load_json(source_log, {})
    source_state = payload.get("task_state", {})
    source_steps = source_state.get("steps", [])
    if not isinstance(source_steps, list) or not source_steps:
        return {
            "task_state": {
                "task_id": f"wf-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                "overall_status": "failed",
                "steps": [],
                "failed_steps": 1,
                "completed_steps": 0,
                "retries_used": 0,
                "error": "source_task_steps_missing",
                "error_class": "config_or_input_error",
            },
            "tool_outputs": {},
        }

    selected_index = -1
    if step_index is not None and 0 <= step_index < len(source_steps):
        selected_index = step_index
    elif tool_name:
        for idx, row in enumerate(source_steps):
            if row.get("tool_name") == tool_name:
                selected_index = idx
                break
    if selected_index < 0:
        return {
            "task_state": {
                "task_id": f"wf-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                "overall_status": "failed",
                "steps": [],
                "failed_steps": 1,
                "completed_steps": 0,
                "retries_used": 0,
                "error": "target_step_not_found",
                "error_class": "config_or_input_error",
            },
            "tool_outputs": {},
        }

    selected_steps = source_steps[selected_index:] if include_downstream else [source_steps[selected_index]]
    replay_steps: list[tuple[str, dict[str, Any]]] = []
    for row in selected_steps:
        replay_steps.append((str(row.get("tool_name", "")), dict(row.get("input_payload", {}) or {})))
    rerun_task_id = f"wf-{datetime.now().strftime('%Y%m%d%H%M%S%f')}-rerun"
    route = str(source_state.get("route", "manager"))
    user_input = str(payload.get("user_input", source_state.get("user_input", "")))
    rerun_from = source_steps[selected_index].get("tool_name", "")
    task_state, tool_outputs = _execute_steps(
        workspace=workspace_path,
        route=route,
        user_input=user_input,
        task_id=rerun_task_id,
        steps=replay_steps,
        parent_task_id=str(task_id),
        rerun_from=str(rerun_from),
    )
    _write_task_log(workspace_path, user_input, task_state)
    return {"task_state": task_state, "tool_outputs": tool_outputs}


__all__ = [
    "build_tool_registry",
    "choose_task_steps",
    "build_action_steps",
    "run_task_plan",
    "rerun_task_step",
]
