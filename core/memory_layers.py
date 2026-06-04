#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三層記憶系統

- short_term: 由執行期/對話記憶維持
- summary: SQLite 中的摘要表
- long_term: SQLite + FAISS 檢索索引
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from core.data_paths import ProjectPaths, resolve_data_root

try:
    import faiss
except Exception:  # pragma: no cover - runtime guarded by caller
    faiss = None


EMBED_DIM = 1024
TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}")
SOURCE_WEIGHTS = {
    "agent_memory_assistant": 0.24,
    "agent_memory_user": 0.20,
    "gpt_history_assistant": 0.16,
    "gpt_history_user": 0.16,
    "chatgpt_database_user": 0.12,
    "chatgpt_database_assistant": 0.10,
    "chatgpt_local_knowledge": 0.06,
}
SOURCE_PRIORITIES = {
    "agent_memory_assistant": 6,
    "agent_memory_user": 5,
    "gpt_history_assistant": 4,
    "gpt_history_user": 4,
    "chatgpt_database_user": 3,
    "chatgpt_database_assistant": 2,
    "chatgpt_local_knowledge": 1,
}


@dataclass
class MemoryPaths:
    root: Path
    sqlite_path: Path
    faiss_path: Path
    meta_path: Path
    vector_cache_path: Path


class ThreeLayerMemory:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).expanduser().resolve()
        paths = ProjectPaths(self.workspace)
        self.root = paths.data / "knowledge_hub" / "memory_layers"
        self.root.mkdir(parents=True, exist_ok=True)
        self.paths = MemoryPaths(
            root=self.root,
            sqlite_path=paths.memory_db,
            faiss_path=paths.faiss_index,
            meta_path=self.root / "long_term_meta.json",
            vector_cache_path=self.root / "long_term_vectors.npz",
        )
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.paths.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    role TEXT,
                    content TEXT NOT NULL,
                    summary TEXT,
                    timestamp TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_long_term_source
                    ON long_term_memory(source, source_id);

                CREATE TABLE IF NOT EXISTS summary_memory (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_source
                    ON summary_memory(source, source_id);
                """
            )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return TOKEN_RE.findall((text or "").lower())

    @staticmethod
    def _summarize_text(text: str, max_len: int = 180) -> str:
        clean = " ".join((text or "").split())
        return clean[:max_len] + ("..." if len(clean) > max_len else "")

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join((text or "").lower().split())

    @classmethod
    def _content_fingerprint(cls, text: str) -> str:
        normalized = cls._normalize_text(text)
        return hashlib.blake2b(normalized.encode("utf-8"), digest_size=16).hexdigest()

    @classmethod
    def _summary_signature(cls, text: str) -> str:
        tokens = sorted(set(cls._tokenize(text)))[:24]
        if not tokens:
            return cls._content_fingerprint(text)[:12]
        return "|".join(tokens)

    @staticmethod
    def _parse_timestamp(value: str) -> float:
        if not value:
            return 0.0
        raw = str(value).strip()
        if not raw:
            return 0.0
        try:
            return float(raw)
        except Exception:
            pass
        normalized = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).timestamp()
        except Exception:
            return 0.0

    @classmethod
    def _source_weight(cls, source: str) -> float:
        return SOURCE_WEIGHTS.get(source, 0.0)

    @classmethod
    def _source_priority(cls, source: str) -> int:
        return SOURCE_PRIORITIES.get(source, 0)

    @classmethod
    def _select_preferred_item(
        cls, current: dict[str, Any], candidate: dict[str, Any]
    ) -> dict[str, Any]:
        current_score = (
            cls._source_priority(current.get("source", "")),
            cls._parse_timestamp(str(current.get("timestamp", ""))),
            len(str(current.get("content", ""))),
        )
        candidate_score = (
            cls._source_priority(candidate.get("source", "")),
            cls._parse_timestamp(str(candidate.get("timestamp", ""))),
            len(str(candidate.get("content", ""))),
        )
        return candidate if candidate_score > current_score else current

    @classmethod
    def _deduplicate_sources(
        cls, sources: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        by_fingerprint: dict[str, dict[str, Any]] = {}
        stats = {
            "input_items": len(sources),
            "exact_duplicates_removed": 0,
        }

        for item in sources:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            fingerprint = cls._content_fingerprint(content)
            item = dict(item)
            item["content_fingerprint"] = fingerprint
            item["summary_signature"] = cls._summary_signature(
                item.get("summary") or content
            )
            existing = by_fingerprint.get(fingerprint)
            if existing is None:
                by_fingerprint[fingerprint] = item
                continue
            by_fingerprint[fingerprint] = cls._select_preferred_item(existing, item)
            stats["exact_duplicates_removed"] += 1

        deduped = list(by_fingerprint.values())
        stats["deduped_items"] = len(deduped)
        return deduped, stats

    def _embed_text(self, text: str) -> np.ndarray:
        vec = np.zeros(EMBED_DIM, dtype=np.float32)
        normalized = " ".join((text or "").lower().split())
        features = list(self._tokenize(normalized))
        features.extend(
            normalized[idx : idx + 2]
            for idx in range(max(0, len(normalized) - 1))
            if normalized[idx : idx + 2].strip()
        )

        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, "big")
            bucket = raw % EMBED_DIM
            sign = 1.0 if ((raw >> 1) & 1) == 0 else -1.0
            vec[bucket] += sign

        norm = math.sqrt(float(np.dot(vec, vec)))
        if norm > 0:
            vec /= norm
        return vec

    def _load_meta(self) -> list[dict[str, Any]]:
        if not self.paths.meta_path.exists():
            return []
        try:
            return json.loads(self.paths.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_meta(self, rows: list[dict[str, Any]]) -> None:
        self.paths.meta_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _load_index(self):
        if faiss is None or not self.paths.faiss_path.exists():
            return None
        index = self._read_faiss_index(self.paths.faiss_path)
        if getattr(index, "d", EMBED_DIM) != EMBED_DIM:
            return None
        return index

    def _save_index(self, index) -> None:
        if faiss is None:
            return
        self.paths.faiss_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            faiss.write_index(index, str(self.paths.faiss_path))
        except Exception:
            shadow = self._faiss_shadow_path(self.paths.faiss_path)
            shadow.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(index, str(shadow))
            shutil.copyfile(shadow, self.paths.faiss_path)

    def _faiss_shadow_path(self, source: Path) -> Path:
        digest = hashlib.blake2b(str(source).encode("utf-8"), digest_size=8).hexdigest()
        return Path(tempfile.gettempdir()) / "cheng_agent_faiss" / f"{digest}.faiss"

    def _read_faiss_index(self, source: Path):
        try:
            return faiss.read_index(str(source))
        except Exception:
            # FAISS on Windows can fail on non-ASCII project paths even when
            # Python itself can see the file. Copy to an ASCII temp path and
            # read from there so Chinese workspace paths remain supported.
            shadow = self._faiss_shadow_path(source)
            shadow.parent.mkdir(parents=True, exist_ok=True)
            if (not shadow.exists()) or shadow.stat().st_mtime < source.stat().st_mtime:
                shutil.copyfile(source, shadow)
            return faiss.read_index(str(shadow))

    def _rank_memory_row(
        self,
        query: str,
        query_tokens: set[str],
        row: sqlite3.Row,
        semantic_score: float = 0.0,
    ) -> dict[str, Any]:
        content = row["content"]
        summary = row["summary"] or ""
        metadata = json.loads(row["metadata_json"])
        content_tokens = set(self._tokenize(content))
        summary_tokens = set(self._tokenize(summary))
        overlap = len(query_tokens & (content_tokens | summary_tokens))
        lexical_score = overlap / max(1, len(query_tokens)) if query_tokens else 0.0
        exact_match = (
            1.0
            if query.strip()
            and query.strip().lower() in f"{summary}\n{content}".lower()
            else 0.0
        )
        source_weight = float(
            metadata.get("source_weight", self._source_weight(row["source"]))
        )
        ranking_score = (
            float(semantic_score) + lexical_score + source_weight + (exact_match * 0.25)
        )
        return {
            "score": float(semantic_score),
            "semantic_score": float(semantic_score),
            "lexical_score": float(lexical_score),
            "source_weight": source_weight,
            "exact_match": exact_match,
            "combined_score": ranking_score,
            "source": row["source"],
            "source_id": row["source_id"],
            "role": row["role"],
            "content": content,
            "summary": summary,
            "timestamp": row["timestamp"],
            "metadata": metadata,
        }

    def _dedupe_results(
        self, results: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]]:
        deduped_results: list[dict[str, Any]] = []
        seen_fingerprints: set[str] = set()
        seen_signatures: list[set[str]] = []
        for item in results:
            metadata = item.get("metadata", {})
            fingerprint = metadata.get(
                "content_fingerprint"
            ) or self._content_fingerprint(item.get("content", ""))
            if fingerprint in seen_fingerprints:
                continue
            signature = metadata.get("summary_signature") or self._summary_signature(
                item.get("summary", "")
            )
            signature_tokens = set(signature.split("|")) if signature else set()
            if any(
                len(signature_tokens & prior) / max(1, len(signature_tokens | prior))
                >= 0.85
                for prior in seen_signatures
            ):
                continue
            seen_fingerprints.add(fingerprint)
            seen_signatures.append(signature_tokens)
            deduped_results.append(item)
            if len(deduped_results) >= top_k:
                break
        return deduped_results

    def _search_sqlite_fallback(self, query: str, top_k: int) -> list[dict[str, Any]]:
        query_tokens = set(self._tokenize(query))
        if not query.strip():
            return []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source, source_id, role, content, summary, timestamp, metadata_json
                FROM long_term_memory
                """
            ).fetchall()

        ranked = [
            self._rank_memory_row(query, query_tokens, row, semantic_score=0.0)
            for row in rows
        ]
        ranked.sort(key=lambda item: item["combined_score"], reverse=True)
        filtered = [
            item
            for item in ranked
            if item["lexical_score"] > 0 or item["exact_match"] > 0
        ]
        if not filtered:
            filtered = [item for item in ranked if item["combined_score"] >= 0.04][
                : max(top_k * 3, 10)
            ]
        return self._dedupe_results(filtered, top_k)

    def rebuild(self, sources: list[dict[str, Any]]) -> dict[str, Any]:
        prepared_sources, dedupe_stats = self._deduplicate_sources(sources)
        embeddings: list[np.ndarray] = []
        meta_rows: list[dict[str, Any]] = []
        now = datetime.now().isoformat()

        with self._connect() as conn:
            conn.execute("DELETE FROM long_term_memory")
            conn.execute("DELETE FROM summary_memory")

            for idx, item in enumerate(prepared_sources):
                source = item["source"]
                source_id = item["source_id"]
                content = item["content"]
                summary = item.get("summary") or self._summarize_text(content)
                role = item.get("role", "")
                timestamp = item.get("timestamp", "")
                metadata = dict(item.get("metadata", {}))
                metadata["content_fingerprint"] = item.get("content_fingerprint", "")
                metadata["summary_signature"] = item.get("summary_signature", "")
                metadata["source_weight"] = self._source_weight(source)

                conn.execute(
                    """
                    INSERT INTO long_term_memory
                    (source, source_id, role, content, summary, timestamp, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source,
                        source_id,
                        role,
                        content,
                        summary,
                        timestamp,
                        json.dumps(metadata, ensure_ascii=False),
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO summary_memory (source, source_id, summary, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (source, source_id, summary, now),
                )

                embeddings.append(self._embed_text(content))
                meta_rows.append(
                    {
                        "index": idx,
                        "source": source,
                        "source_id": source_id,
                        "role": role,
                        "summary": summary,
                        "timestamp": timestamp,
                        "content_fingerprint": item.get("content_fingerprint", ""),
                        "summary_signature": item.get("summary_signature", ""),
                    }
                )

            conn.commit()

        faiss_mode = faiss is not None
        if faiss_mode:
            matrix = (
                np.vstack(embeddings).astype(np.float32)
                if embeddings
                else np.zeros((0, EMBED_DIM), dtype=np.float32)
            )
            index = faiss.IndexFlatIP(EMBED_DIM)
            if len(matrix):
                index.add(matrix)
            self._save_index(index)
        self._save_meta(meta_rows)

        return {
            "items_indexed": len(meta_rows),
            "sqlite_path": str(self.paths.sqlite_path),
            "faiss_path": str(self.paths.faiss_path),
            "meta_path": str(self.paths.meta_path),
            "dedupe": dedupe_stats,
            "faiss_mode": faiss_mode,
            "degraded_mode": None if faiss_mode else "sqlite_only",
        }

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if faiss is None:
            return self._search_sqlite_fallback(query, top_k)

        index = self._load_index()
        meta_rows = self._load_meta()
        if index is None or not meta_rows:
            return self._search_sqlite_fallback(query, top_k)
        if not query.strip():
            return []

        query_vec = self._embed_text(query).reshape(1, -1)
        candidate_k = min(max(top_k * 8, 24), len(meta_rows))
        scores, indices = index.search(query_vec, candidate_k)
        query_tokens = set(self._tokenize(query))

        results: list[dict[str, Any]] = []
        with self._connect() as conn:
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(meta_rows):
                    continue
                meta = meta_rows[idx]
                row = conn.execute(
                    """
                    SELECT source, source_id, role, content, summary, timestamp, metadata_json
                    FROM long_term_memory
                    WHERE source = ? AND source_id = ?
                    """,
                    (meta["source"], meta["source_id"]),
                ).fetchone()
                if not row:
                    continue
                results.append(
                    self._rank_memory_row(
                        query, query_tokens, row, semantic_score=float(score)
                    )
                )
        results.sort(key=lambda item: item["combined_score"], reverse=True)
        if query_tokens:
            filtered = [item for item in results if item["lexical_score"] > 0]
        else:
            filtered = [item for item in results if item["score"] > 0.2]
        if not filtered:
            filtered = [item for item in results if item["combined_score"] > 0.15][
                : max(top_k * 3, 10)
            ]
        return self._dedupe_results(filtered, top_k)

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM long_term_memory").fetchone()[0]
            by_source = conn.execute(
                "SELECT source, COUNT(*) AS c FROM long_term_memory GROUP BY source ORDER BY c DESC"
            ).fetchall()
        return {
            "sqlite_path": str(self.paths.sqlite_path),
            "faiss_path": str(self.paths.faiss_path),
            "meta_path": str(self.paths.meta_path),
            "total_items": total,
            "by_source": {row["source"]: row["c"] for row in by_source},
            "faiss_available": faiss is not None,
            "faiss_file_exists": self.paths.faiss_path.exists(),
            "faiss_ready": faiss is not None and self.paths.faiss_path.exists(),
            "source_weights": SOURCE_WEIGHTS,
        }


def collect_memory_sources(workspace: str | Path) -> list[dict[str, Any]]:
    workspace = Path(workspace).expanduser().resolve()
    paths = ProjectPaths(workspace)
    sources: list[dict[str, Any]] = []

    def append_source(
        source: str,
        source_id: str,
        role: str,
        content: str,
        timestamp: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        text = " ".join(str(content or "").split()).strip()
        if len(text) < 8:
            return
        if len(text) > 5000:
            text = text[:5000]
        sources.append(
            {
                "source": source,
                "source_id": source_id,
                "role": role,
                "content": text,
                "summary": ThreeLayerMemory._summarize_text(text),
                "timestamp": str(timestamp or ""),
                "metadata": dict(metadata or {}),
            }
        )

    local_kb = paths.llama_data / "local_knowledge" / "local_knowledge_base.json"
    if local_kb.exists():
        try:
            data = json.loads(local_kb.read_text(encoding="utf-8"))
            for item in data:
                content = str(item.get("content", "")).strip()
                append_source(
                    "chatgpt_local_knowledge",
                    str(item.get("message_id") or f"lk_{len(sources)}"),
                    str(item.get("role", "")),
                    content,
                    str(item.get("timestamp", "")),
                    {"conversation_id": item.get("conversation_id", "")},
                )
        except Exception:
            pass

    chatgpt_db = paths.llama_data / "local_knowledge" / "complete_chatgpt_database.json"
    if chatgpt_db.exists():
        try:
            payload = json.loads(chatgpt_db.read_text(encoding="utf-8"))
            conversations = payload.get("data", {}).get("conversations", [])
            if not isinstance(conversations, list):
                conversations = []
            for conv_idx, conv in enumerate(conversations):
                if not isinstance(conv, dict):
                    continue
                conv_id = str(conv.get("id") or conv.get("conversation_id") or f"conv_{conv_idx}")
                title = str(conv.get("title") or "")
                timestamp = str(conv.get("create_time") or conv.get("update_time") or "")
                user_chunks: list[str] = []
                assistant_chunks: list[str] = []
                mapping = conv.get("mapping", {})
                if isinstance(mapping, dict):
                    iterable = mapping.values()
                elif isinstance(mapping, list):
                    iterable = mapping
                else:
                    iterable = []
                for msg_data in iterable:
                    if not isinstance(msg_data, dict):
                        continue
                    message = msg_data.get("message") if "message" in msg_data else msg_data
                    if not isinstance(message, dict):
                        continue
                    role = str(message.get("author", {}).get("role", "")).strip()
                    content = message.get("content", {})
                    parts = content.get("parts", []) if isinstance(content, dict) else []
                    text_parts = [part for part in parts if isinstance(part, str) and part.strip()]
                    text = "\n".join(text_parts).strip()
                    if not text:
                        continue
                    if role == "user":
                        user_chunks.append(text)
                    elif role == "assistant":
                        assistant_chunks.append(text)
                common_meta = {
                    "conversation_id": conv_id,
                    "title": title,
                    "source_kind": "complete_chatgpt_database",
                }
                if user_chunks:
                    append_source(
                        "chatgpt_database_user",
                        f"chatgptdb:{conv_id}:user",
                        "user",
                        "\n---\n".join([title, *user_chunks]) if title else "\n---\n".join(user_chunks),
                        timestamp,
                        {**common_meta, "message_count": len(user_chunks)},
                    )
                if assistant_chunks:
                    append_source(
                        "chatgpt_database_assistant",
                        f"chatgptdb:{conv_id}:assistant",
                        "assistant",
                        "\n---\n".join([title, *assistant_chunks]) if title else "\n---\n".join(assistant_chunks),
                        timestamp,
                        {**common_meta, "message_count": len(assistant_chunks)},
                    )
        except Exception:
            pass

    agent_conversations = paths.data / "agent_memories" / "conversations.json"
    if agent_conversations.exists():
        try:
            data = json.loads(agent_conversations.read_text(encoding="utf-8"))
            for conv_id, conv in data.items():
                for idx, msg in enumerate(conv.get("messages", [])):
                    user = str(msg.get("user", "")).strip()
                    assistant = str(msg.get("assistant", "")).strip()
                    timestamp = str(msg.get("timestamp", ""))
                    if user and len(user) >= 8:
                        append_source(
                            "agent_memory_user",
                            f"{conv_id}:u:{idx}",
                            "user",
                            user,
                            timestamp,
                            {"agent_name": conv.get("agent_name", "")},
                        )
                    if assistant and len(assistant) >= 8:
                        append_source(
                            "agent_memory_assistant",
                            f"{conv_id}:a:{idx}",
                            "assistant",
                            assistant,
                            timestamp,
                            {"agent_name": conv.get("agent_name", "")},
                        )
        except Exception:
            pass

    # GPT Chat History from SQLite
    chat_db = paths.root / "instance" / "chat_history.db"
    if chat_db.exists():
        try:
            with sqlite3.connect(chat_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, user_message, ai_response, agent_type, model_used, timestamp FROM chat_history"
                ).fetchall()
                for row in rows:
                    msg_id = row["id"]
                    user_msg = str(row["user_message"] or "").strip()
                    ai_resp = str(row["ai_response"] or "").strip()
                    ts = str(row["timestamp"] or "")
                    agent = row["agent_type"] or "unknown"
                    
                    if user_msg and len(user_msg) >= 8:
                        append_source(
                            "gpt_history_user",
                            f"gh:{msg_id}:u",
                            "user",
                            user_msg,
                            ts,
                            {"agent": agent, "model": row["model_used"]},
                        )
                    if ai_resp and len(ai_resp) >= 8:
                        append_source(
                            "gpt_history_assistant",
                            f"gh:{msg_id}:a",
                            "assistant",
                            ai_resp,
                            ts,
                            {"agent": agent, "model": row["model_used"]},
                        )
        except Exception:
            pass

    return sources
