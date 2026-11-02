def test_expected_rank_accepts_normalized_suffix_and_source_fallback():
    from tools.evaluate_knowledge_retrieval import expected_rank

    matches = [
        {"source": "knowledge_document", "metadata": {"path": "dev\\OTHER.md"}},
        {"source": "knowledge_document", "metadata": {"path": "docs\\runbooks\\TARGET.md"}},
    ]
    assert expected_rank(matches, {"expected_paths": ["runbooks/target.md"]}) == 2
    assert expected_rank(matches, {"expected_sources": ["knowledge_document"]}) == 1


def test_evaluation_report_never_copies_retrieved_content():
    from tools.evaluate_knowledge_retrieval import evaluate

    class Hub:
        def search(self, query, top_k):
            return {
                "ok": True,
                "matches": [
                    {
                        "source": "knowledge_document",
                        "content": "private text must not leak",
                        "metadata": {"path": "docs/target.md"},
                    }
                ],
            }

    report = evaluate(
        Hub(),
        [{"id": "one", "query": "target", "expected_paths": ["target.md"]}],
        5,
    )
    assert report["hit_rate"] == 1.0
    assert "private text must not leak" not in str(report)


def test_evaluation_report_exposes_split_metrics_and_case_categories():
    from tools.evaluate_knowledge_retrieval import evaluate

    class Hub:
        def search(self, query, top_k):
            if query == "missing":
                return {"ok": True, "matches": []}
            if query == "stale":
                return {
                    "ok": True,
                    "matches": [
                        {"source": "knowledge_document", "metadata": {"path": "old.md"}}
                    ],
                }
            return {
                "ok": True,
                "matches": [
                    {
                        "source": "knowledge_document",
                        "content": "must stay out of report",
                        "metadata": {"path": "docs/target.md"},
                    }
                ],
            }

    report = evaluate(
        Hub(),
        [
            {"id": "hit", "query": "hit", "expected_paths": ["target.md"]},
            {"id": "missing", "query": "missing", "category": "no_hit", "expect_hit": False},
            {
                "id": "conflict",
                "query": "conflict",
                "category": "conflict",
                "expected_paths": ["target.md", "other.md"],
            },
            {
                "id": "stale",
                "query": "stale",
                "category": "stale",
                "stale_paths": ["old.md"],
                "expect_hit": False,
            },
        ],
        5,
    )

    assert report["metrics"]["hit_rate"] == 1.0
    assert report["metrics"]["mrr"] == 1.0
    assert report["metrics"]["citation_correctness"] == 1.0
    assert report["metrics"]["privacy_leakage"] == 0
    assert report["metrics"]["no_hit"]["false_positive"] == 0
    assert report["metrics"]["stale"]["retrieved"] == 1
    assert report["privacy"] == "metadata_only_no_retrieved_content"


def test_eval_config_has_broad_case_coverage():
    import json
    from pathlib import Path

    config = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "knowledge_retrieval_eval.json")
        .read_text(encoding="utf-8")
    )
    cases = config["cases"]
    assert 30 <= len(cases) <= 50
    categories = {case.get("category", "hit") for case in cases}
    assert {"no_hit", "conflict", "stale"} <= categories
