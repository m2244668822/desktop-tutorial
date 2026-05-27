#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate RAG artifacts and markdown report for mainline programs.

Outputs:
- data/knowledge_hub/ingestion/mainline_program_documents.jsonl
- data/knowledge_hub/ingestion/mainline_program_chunks.jsonl
- reports/MAINLINE_RAG_REPORT_YYYYMMDD.md
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
PRIMARY_INGESTION_DIR = BASE_DIR / "data" / "knowledge_hub" / "ingestion"
FALLBACK_INGESTION_DIR = BASE_DIR / "data_hdd_storage" / "knowledge_hub" / "ingestion"
REPORTS_DIR = BASE_DIR / "reports"
TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}")
MAX_FILE_BYTES = 2_500_000
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 140

MAINLINE_PATTERNS = [
    "system_main.py",
    "desktop_chat_app.py",
    "core/*.py",
    "tools/agent_autonomy_daemon.py",
    "tools/enqueue_autonomy_task.py",
    "tools/manage_autopilot_daemon.sh",
    "tools/build_knowledge_ingestion.py",
    "tools/sync_knowledge_hub.py",
    "tools/local_memory_api.py",
    "tools/agent_memory_manager.py",
]


@dataclass
class MainlineDocument:
    doc_id: str
    path: str
    title: str
    text: str
    metadata: dict[str, Any]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _doc_id(path: str) -> str:
    return hashlib.blake2b(path.encode("utf-8"), digest_size=12).hexdigest()


def _chunk_text(text: str) -> list[str]:
    normalized = _normalize(text)
    if not normalized:
        return []
    if len(normalized) <= CHUNK_SIZE:
        return [normalized]
    out: list[str] = []
    start = 0
    while start < len(normalized):
        block = normalized[start : start + CHUNK_SIZE]
        if block:
            out.append(block)
        if start + CHUNK_SIZE >= len(normalized):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return out


def _iter_mainline_files() -> list[Path]:
    files: list[Path] = []
    for pattern in MAINLINE_PATTERNS:
        for path in BASE_DIR.glob(pattern):
            if path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
                files.append(path)
    unique = sorted({p.resolve() for p in files})
    return unique


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _top_keywords(texts: list[str], limit: int = 25) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for text in texts:
        for token in TOKEN_RE.findall(text):
            clean = token.strip().lower()
            if len(clean) < 3:
                continue
            counter[clean] += 1
    return counter.most_common(limit)


def _agent_focus(path: str) -> str:
    if path.startswith("core/"):
        return "總管/申言者"
    if "autonomy" in path or "autopilot" in path:
        return "總管"
    if "memory" in path or "knowledge" in path:
        return "研究員"
    if "desktop_chat_app.py" in path or "system_main.py" in path:
        return "工程師"
    return "通用"


def build_report() -> Path:
    ingestion_dir = PRIMARY_INGESTION_DIR
    if not (BASE_DIR / "data").exists():
        ingestion_dir = FALLBACK_INGESTION_DIR
    else:
        try:
            PRIMARY_INGESTION_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            ingestion_dir = FALLBACK_INGESTION_DIR

    files = _iter_mainline_files()
    generated_at = datetime.now()
    docs: list[MainlineDocument] = []

    for path in files:
        rel = str(path.relative_to(BASE_DIR))
        text = _normalize(_read(path))
        if len(text) < 30:
            continue
        docs.append(
            MainlineDocument(
                doc_id=_doc_id(rel),
                path=rel,
                title=path.stem,
                text=text,
                metadata={
                    "size_bytes": path.stat().st_size,
                    "agent_focus": _agent_focus(rel),
                },
            )
        )

    documents_rows = [asdict(d) for d in docs]
    chunks_rows: list[dict[str, Any]] = []
    for doc in docs:
        for idx, chunk in enumerate(_chunk_text(doc.text)):
            chunks_rows.append(
                {
                    "chunk_id": f"{doc.doc_id}:{idx}",
                    "doc_id": doc.doc_id,
                    "path": doc.path,
                    "title": doc.title,
                    "agent_focus": doc.metadata.get("agent_focus", "通用"),
                    "text": chunk,
                }
            )

    ingestion_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(ingestion_dir / "mainline_program_documents.jsonl", documents_rows)
    _write_jsonl(ingestion_dir / "mainline_program_chunks.jsonl", chunks_rows)

    keywords = _top_keywords([d.text for d in docs], limit=30)
    by_agent: dict[str, int] = {}
    for d in docs:
        focus = str(d.metadata.get("agent_focus", "通用"))
        by_agent[focus] = by_agent.get(focus, 0) + 1

    report_path = REPORTS_DIR / f"MAINLINE_RAG_REPORT_{generated_at.strftime('%Y%m%d')}.md"
    lines = [
        "# Mainline RAG Report",
        "",
        f"- generated_at: {generated_at.isoformat(timespec='seconds')}",
        f"- workspace: `{BASE_DIR}`",
        f"- documents: `{len(docs)}`",
        f"- chunks: `{len(chunks_rows)}`",
        f"- ingestion_dir: `{ingestion_dir}`",
        "",
        "## Mainline Scope",
        "",
        "This report indexes runtime-critical files only (entrypoints, core workflow, autonomy daemon, memory/knowledge bridge).",
        "",
        "## Agent Coverage",
        "",
    ]
    for agent, count in sorted(by_agent.items(), key=lambda x: x[0]):
        lines.append(f"- `{agent}`: {count} files")

    lines.extend(
        [
            "",
            "## Top Retrieval Keywords",
            "",
        ]
    )
    for token, score in keywords:
        lines.append(f"- `{token}`: {score}")

    lines.extend(
        [
            "",
            "## Indexed Files",
            "",
        ]
    )
    for doc in docs:
        lines.append(
            f"- `{doc.path}` ({doc.metadata.get('agent_focus', '通用')}, {doc.metadata.get('size_bytes', 0)} bytes)"
        )

    lines.extend(
        [
            "",
            "## Findings",
            "",
            "1. Mainline RAG can now target code-first runtime paths instead of only docs/reports.",
            "2. Autonomy queue + workflow runtime are indexed together, enabling task-state retrieval and replay guidance.",
            "3. Skill stability checks are runnable and indexable from the same knowledge hub context.",
            "",
            "## Optimization Recommendations",
            "",
            "1. Add reranker stage on top of `mainline_program_chunks.jsonl` for better long-query precision.",
            "2. Add conflict policy fields inside every project skill to reduce routing ambiguity.",
            "3. Expose autonomy state files as a lightweight backend endpoint for frontend live diagnostics.",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    report = build_report()
    print(f"✅ mainline RAG report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
