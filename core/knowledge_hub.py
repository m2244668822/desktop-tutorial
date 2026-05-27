#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Knowledge Hub CNS entrypoint.

Phase-1 goal:
- Provide a single stable API for knowledge status/search/rebuild.
- Keep existing app behavior unchanged while enabling "library mode".
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.data_paths import ProjectPaths
from core.memory_layers import ThreeLayerMemory, collect_memory_sources


class KnowledgeHub:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).expanduser().resolve()
        self._memory = ThreeLayerMemory(self.workspace)
        self._lock = threading.Lock()
        self._last_rebuild_at = ""
        self._last_error = ""

    def status(self) -> dict[str, Any]:
        with self._lock:
            stats = self._memory.stats()
            paths = ProjectPaths(self.workspace)
            sqlite_path = Path(str(stats.get("sqlite_path", "")))
            faiss_path = Path(str(stats.get("faiss_path", "")))
            meta_path = Path(str(stats.get("meta_path", "")))
            chatgpt_database_path = (
                paths.llama_data / "local_knowledge" / "complete_chatgpt_database.json"
            )
            chatgpt_local_index_path = (
                paths.llama_data / "local_knowledge" / "local_knowledge_base.json"
            )
            total_items = int(stats.get("total_items", 0) or 0)
            sqlite_ready = sqlite_path.exists() and total_items > 0
            faiss_ready = faiss_path.exists() and meta_path.exists() and total_items > 0
            return {
                "ok": True,
                "workspace": str(self.workspace),
                "total_items": total_items,
                "sqlite_ready": sqlite_ready,
                "faiss_ready": faiss_ready,
                "chatgpt_database_ready": chatgpt_database_path.exists()
                or chatgpt_local_index_path.exists(),
                "chatgpt_database_path": str(chatgpt_database_path),
                "chatgpt_local_index_path": str(chatgpt_local_index_path),
                "by_source": stats.get("by_source", {}),
                "sqlite_path": str(sqlite_path),
                "faiss_path": str(faiss_path),
                "meta_path": str(meta_path),
                "manifest_path": str(paths.knowledge_manifest),
                "manifest_exists": paths.knowledge_manifest.exists(),
                "last_rebuild_at": self._last_rebuild_at,
                "last_error": self._last_error,
            }

    def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        q = str(query or "").strip()
        if not q:
            return {"ok": False, "error": "query_required", "matches": []}
        with self._lock:
            matches = self._memory.search(q, top_k=max(1, min(int(top_k), 20)))
        return {
            "ok": True,
            "query": q,
            "top_k": max(1, min(int(top_k), 20)),
            "matches": matches,
            "count": len(matches),
        }

    def rebuild(self) -> dict[str, Any]:
        with self._lock:
            try:
                sources = collect_memory_sources(self.workspace)
                result = self._memory.rebuild(sources)
                self._last_rebuild_at = datetime.now().isoformat()
                self._last_error = ""
                return {
                    "ok": True,
                    "rebuilt": True,
                    "sources_count": len(sources),
                    "result": result,
                    "rebuilt_at": self._last_rebuild_at,
                }
            except Exception as exc:
                if "FAISS" in str(exc).upper():
                    # Degrade gracefully: keep hub searchable via SQLite fallback.
                    self._last_error = ""
                    return {
                        "ok": True,
                        "rebuilt": False,
                        "degraded_mode": "sqlite_only",
                        "reason": str(exc),
                        "sources_count": len(collect_memory_sources(self.workspace)),
                    }
                self._last_error = str(exc)
                return {
                    "ok": False,
                    "rebuilt": False,
                    "error": str(exc),
                    "sources_count": 0,
                }
