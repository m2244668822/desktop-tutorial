#!/usr/bin/env python3
"""Evaluate Knowledge Hub retrieval without writing private result content."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.knowledge_hub import KnowledgeHub


def _normalized_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip().lower()


def expected_rank(matches: list[dict[str, Any]], case: dict[str, Any]) -> int | None:
    expected_paths = {_normalized_path(item) for item in case.get("expected_paths", [])}
    expected_sources = {str(item).strip() for item in case.get("expected_sources", [])}
    for rank, match in enumerate(matches, start=1):
        metadata = match.get("metadata", {}) if isinstance(match, dict) else {}
        path = _normalized_path(metadata.get("path", ""))
        source = str(match.get("source", "")) if isinstance(match, dict) else ""
        path_hit = any(path.endswith(expected) for expected in expected_paths if expected)
        source_hit = source in expected_sources
        if path_hit or source_hit:
            return rank
    return None


def evaluate(hub: KnowledgeHub, cases: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    hub_status: dict[str, Any] = {}
    try:
        raw_status = hub.status()
        for key in ("total_items", "sqlite_ready", "faiss_ready", "manifest_exists"):
            if key in raw_status:
                hub_status[key] = raw_status[key]
    except Exception as exc:  # pragma: no cover - defensive runtime boundary
        hub_status = {"status_error": type(exc).__name__}
    results: list[dict[str, Any]] = []
    positive_cases = 0
    hits = 0
    reciprocal_rank_total = 0.0
    citation_hits = 0
    no_hit_cases = 0
    no_hit_false_positives = 0
    stale_cases = 0
    stale_retrieved = 0
    privacy_leakage = 0
    for case in cases:
        query = str(case.get("query", "")).strip()
        if not query:
            continue
        response = hub.search(query, top_k=top_k)
        matches = response.get("matches", []) if response.get("ok") else []
        rank = expected_rank(matches, case)
        category = str(case.get("category", "hit") or "hit").strip().lower()
        expect_hit = bool(case.get("expect_hit", category not in {"no_hit", "stale"}))
        if expect_hit:
            positive_cases += 1
            hits += int(rank is not None)
            reciprocal_rank_total += 0.0 if rank is None else 1.0 / rank
            citation_hits += int(rank == 1)
        if category == "no_hit":
            no_hit_cases += 1
            no_hit_false_positives += int(rank is not None)
        stale_paths = {_normalized_path(item) for item in case.get("stale_paths", [])}
        stale_match = any(
            _normalized_path((match.get("metadata", {}) or {}).get("path", "")) in stale_paths
            for match in matches
            if isinstance(match, dict)
        )
        if category == "stale":
            stale_cases += 1
            stale_retrieved += int(stale_match)
        # Deliberately retain only source/path/rank evidence, never memory text.
        evidence = []
        for index, match in enumerate(matches, start=1):
            metadata = match.get("metadata", {}) if isinstance(match, dict) else {}
            evidence.append(
                {
                    "rank": index,
                    "source": str(match.get("source", "")),
                    "path": str(metadata.get("path", "")),
                }
            )
        results.append(
            {
                "id": str(case.get("id", query)),
                "query": query,
                "hit": rank is not None,
                "rank": rank,
                "category": category,
                "expect_hit": expect_hit,
                "citation_correct": rank == 1 if expect_hit else None,
                "stale_retrieved": stale_match,
                "evidence": evidence,
            }
        )
    count = len(results)
    hit_rate = hits / positive_cases if positive_cases else 0.0
    mrr = reciprocal_rank_total / positive_cases if positive_cases else 0.0
    citation_correctness = citation_hits / positive_cases if positive_cases else 0.0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_k": top_k,
        "cases": count,
        "hits": hits,
        "hit_rate": round(hit_rate, 4),
        "mrr": round(mrr, 4),
        "metrics": {
            "hit_rate": round(hit_rate, 4),
            "mrr": round(mrr, 4),
            "citation_correctness": round(citation_correctness, 4),
            "privacy_leakage": privacy_leakage,
            "no_hit": {
                "cases": no_hit_cases,
                "false_positive": no_hit_false_positives,
            },
            "stale": {
                "cases": stale_cases,
                "retrieved": stale_retrieved,
            },
        },
        "hub": hub_status,
        "privacy": "metadata_only_no_retrieved_content",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=BASE_DIR)
    parser.add_argument(
        "--cases", type=Path, default=BASE_DIR / "config" / "knowledge_retrieval_eval.json"
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    report = evaluate(KnowledgeHub(args.workspace), cases, max(1, min(args.top_k, 20)))
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["hit_rate"] >= float(payload.get("minimum_hit_rate", 0.0)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
