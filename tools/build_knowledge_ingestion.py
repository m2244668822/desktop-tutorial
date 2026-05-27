#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建立知識中樞文件導入管線。

輸出：
- data/knowledge_hub/ingestion/documents.jsonl
- data/knowledge_hub/ingestion/chunks.jsonl
- data/knowledge_hub/ingestion/summary.json
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".md", ".txt", ".json", ".html", ".jsonl"}
MAX_FILE_BYTES = 2_000_000
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120


def resolve_data_root(base_dir: Path) -> Path:
    """Resolve a writable data root across macOS symlink and Windows fallback."""
    primary = base_dir / "data"
    if primary.is_dir():
        return primary

    fallback = base_dir / "data_hdd_storage"
    if fallback.is_dir():
        return fallback

    # If `data` is a broken symlink or plain file on Windows, prefer fallback.
    if primary.exists() and not primary.is_dir():
        return fallback

    return primary


@dataclass
class IngestedDocument:
    doc_id: str
    source: str
    path: str
    title: str
    text: str
    metadata: dict[str, Any]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _doc_id(source: str, path: str) -> str:
    raw = f"{source}:{path}"
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=12).hexdigest()


def _iter_text_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        paths.append(path)
    return paths


def _load_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _chunk_text(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= CHUNK_SIZE:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        chunk = normalized[start : start + CHUNK_SIZE]
        if chunk:
            chunks.append(chunk)
        if start + CHUNK_SIZE >= len(normalized):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def ingest_local_knowledge(local_knowledge_dir: Path) -> list[IngestedDocument]:
    docs: list[IngestedDocument] = []
    kb_path = local_knowledge_dir / "local_knowledge_base.json"
    if kb_path.exists():
        try:
            data = json.loads(kb_path.read_text(encoding="utf-8"))
        except Exception:
            data = []
        for idx, item in enumerate(data):
            content = _normalize_text(str(item.get("content", "")))
            if len(content) < 20:
                continue
            source_path = f"local_knowledge_base.json#{idx}"
            docs.append(
                IngestedDocument(
                    doc_id=_doc_id("local_knowledge", source_path),
                    source="local_knowledge",
                    path=source_path,
                    title=item.get("conversation_title", "")
                    or item.get("conversation_id", "")
                    or f"local_knowledge_{idx}",
                    text=content,
                    metadata={
                        "role": item.get("role", ""),
                        "conversation_id": item.get("conversation_id", ""),
                        "timestamp": item.get("timestamp", ""),
                    },
                )
            )

    for path in _iter_text_files(local_knowledge_dir):
        if path.name == "local_knowledge_base.json":
            continue
        text = _normalize_text(_load_text_file(path))
        if len(text) < 20:
            continue
        rel = path.relative_to(local_knowledge_dir)
        docs.append(
            IngestedDocument(
                doc_id=_doc_id("local_knowledge_file", str(rel)),
                source="local_knowledge_file",
                path=str(rel),
                title=path.stem,
                text=text,
                metadata={"suffix": path.suffix.lower()},
            )
        )
    return docs


def ingest_text_roots(source_name: str, root: Path) -> list[IngestedDocument]:
    docs: list[IngestedDocument] = []
    if not root.exists():
        return docs
    for path in _iter_text_files(root):
        text = _normalize_text(_load_text_file(path))
        if len(text) < 20:
            continue
        rel = path.relative_to(root)
        docs.append(
            IngestedDocument(
                doc_id=_doc_id(source_name, str(rel)),
                source=source_name,
                path=str(rel),
                title=path.stem,
                text=text,
                metadata={"suffix": path.suffix.lower()},
            )
        )
    return docs


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def build_pipeline(base_dir: Path = BASE_DIR) -> dict[str, Any]:
    data_root = resolve_data_root(base_dir)
    hub_dir = data_root / "knowledge_hub"
    ingestion_dir = hub_dir / "ingestion"
    local_knowledge_dir = base_dir / "500" / "llama32-chat" / "data" / "local_knowledge"
    docs_dir = base_dir / "docs"
    reports_dir = base_dir / "reports"
    logs_dir = base_dir / "logs"

    documents: list[IngestedDocument] = []
    documents.extend(ingest_local_knowledge(local_knowledge_dir))
    documents.extend(ingest_text_roots("docs", docs_dir))
    documents.extend(ingest_text_roots("reports", reports_dir))
    documents.extend(ingest_text_roots("logs", logs_dir))

    deduped: dict[str, IngestedDocument] = {}
    for doc in documents:
        if doc.doc_id not in deduped:
            deduped[doc.doc_id] = doc
    final_docs = list(deduped.values())

    ingestion_dir.mkdir(parents=True, exist_ok=True)
    document_rows = [asdict(doc) for doc in final_docs]
    write_jsonl(ingestion_dir / "documents.jsonl", document_rows)

    chunk_rows: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    for doc in final_docs:
        source_counts[doc.source] = source_counts.get(doc.source, 0) + 1
        for idx, chunk in enumerate(_chunk_text(doc.text)):
            chunk_rows.append(
                {
                    "chunk_id": f"{doc.doc_id}:{idx}",
                    "doc_id": doc.doc_id,
                    "source": doc.source,
                    "path": doc.path,
                    "title": doc.title,
                    "text": chunk,
                    "metadata": doc.metadata,
                }
            )
    write_jsonl(ingestion_dir / "chunks.jsonl", chunk_rows)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "data_root": str(data_root),
        "hub_dir": str(hub_dir),
        "documents_path": str(ingestion_dir / "documents.jsonl"),
        "chunks_path": str(ingestion_dir / "chunks.jsonl"),
        "document_count": len(final_docs),
        "chunk_count": len(chunk_rows),
        "source_counts": source_counts,
        "notes": [
            "優先導入整理後的 local_knowledge，而不是直接暴力掃描整包 opai 本地原始資料。",
            "原始 opai 本地資料仍保留在 data/knowledge_hub/chatgpt_export 作為來源備查。",
            "這條管線可作為 AnythingLLM 風格的 ingestion 前置層。",
        ],
    }
    (ingestion_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    summary = build_pipeline(BASE_DIR)
    print("✅ 知識導入管線已建立")
    print(f"   documents: {summary['document_count']}")
    print(f"   chunks: {summary['chunk_count']}")
    print(f"   output: {summary['documents_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
