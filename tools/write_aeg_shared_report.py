#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from core.data_paths import resolve_data_root


DATA_ROOT = resolve_data_root(BASE)
AEG_JSON = DATA_ROOT / "knowledge_hub" / "aeg_keyword_graph.json"
REPORTS_DIR = BASE / "reports"
OUT = REPORTS_DIR / "AEG_SHARED_REPORT.md"


def _is_private_use(ch: str) -> bool:
    code = ord(ch)
    return 0xE000 <= code <= 0xF8FF


def _looks_garbled(token: str) -> bool:
    raw = str(token or "").strip()
    if not raw:
        return True
    if any(_is_private_use(ch) for ch in raw):
        return True
    return "??" in raw or "\ufffd" in raw


def _fmt_items(items: list[Any], key: str, n: int = 20) -> str:
    lines: list[str] = []
    for idx, item in enumerate(items[:n], start=1):
        if isinstance(item, dict):
            label = str(item.get(key, "")).strip()
            score = item.get("count", item.get("weight", item.get("score", "")))
            lines.append(f"{idx}. `{label}` ({score})")
        else:
            lines.append(f"{idx}. `{item}`")
    return "\n".join(lines) if lines else "- no data"


def _normalize_top_edges(payload: dict[str, Any]) -> list[dict[str, Any]]:
    top_edges = payload.get("top_pairs", [])
    if isinstance(top_edges, list) and top_edges:
        return [e for e in top_edges if isinstance(e, dict)]

    edges = payload.get("edges", [])
    if not isinstance(edges, list):
        return []

    normalized: list[dict[str, Any]] = []
    for row in edges:
        if not isinstance(row, dict):
            continue
        a = str(row.get("a", "")).strip()
        b = str(row.get("b", "")).strip()
        pair = f"{a} <-> {b}".strip(" <-> ")
        normalized.append({"pair": pair, "count": row.get("weight", 0)})
    return normalized


def build_report(payload: dict[str, Any]) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    top_keywords = payload.get("top_keywords", [])
    if not isinstance(top_keywords, list) or not top_keywords:
        top_keywords = payload.get("keywords", [])
    if not isinstance(top_keywords, list):
        top_keywords = []

    top_edges = _normalize_top_edges(payload)
    kw_count = payload.get("keywords_count")
    if kw_count is None:
        kw_count = len(top_keywords)

    readable_keywords = []
    garbled_keywords = []
    for item in top_keywords:
        if not isinstance(item, dict):
            continue
        token = str(item.get("keyword", "")).strip()
        if _looks_garbled(token):
            garbled_keywords.append(item)
        else:
            readable_keywords.append(item)

    total_kw = len(top_keywords)
    readable_ratio = (len(readable_keywords) / total_kw) if total_kw else 0.0

    parts = [
        "# AEG Shared Retrieval Report",
        "",
        f"- generated_at: `{now}`",
        f"- source_file: `{AEG_JSON}`",
        f"- sources_seen: `{payload.get('sources_seen', 0)}`",
        f"- text_items: `{payload.get('text_items', 0)}`",
        f"- keywords_count: `{kw_count}`",
        "",
        "## Completeness Check",
        f"- readable_keywords: `{len(readable_keywords)}/{total_kw}` ({readable_ratio:.1%})",
        f"- suspected_garbled_keywords: `{len(garbled_keywords)}`",
        f"- skipped_garbled_tokens_at_build: `{payload.get('skipped_garbled_tokens', 0)}`",
        "",
        "## Top Keywords (readable-first)",
        _fmt_items(readable_keywords or top_keywords, key="keyword", n=30),
        "",
        "## Top Keyword Pairs",
        _fmt_items(top_edges, key="pair", n=30),
        "",
    ]

    if garbled_keywords:
        parts.extend(
            [
                "## Suspected Garbled Keyword Samples",
                _fmt_items(garbled_keywords, key="keyword", n=20),
                "",
            ]
        )

    parts.extend(
        [
            "## Optimization Notes",
            "- Clean source corpora that contain private-use or replacement characters.",
            "- Move high-frequency clean keywords into RAG seed prompts/allowlists.",
            "- Keep this report in scheduler cycles to monitor data quality drift.",
            "",
        ]
    )
    return "\n".join(parts)


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if not AEG_JSON.exists():
        OUT.write_text(
            "# AEG Shared Retrieval Report\n\n- `aeg_keyword_graph.json` is missing. Run AEG graph build first.\n",
            encoding="utf-8",
        )
        print(f"[aeg-report] no aeg json, wrote placeholder -> {OUT}")
        return 0

    payload = json.loads(AEG_JSON.read_text(encoding="utf-8"))
    OUT.write_text(build_report(payload), encoding="utf-8")
    print(f"[aeg-report] updated -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
