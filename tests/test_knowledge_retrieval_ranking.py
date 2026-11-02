from pathlib import Path


def test_authoritative_knowledge_document_beats_memory_noise_for_doc_query(tmp_path):
    from core.memory_layers import ThreeLayerMemory

    memory = ThreeLayerMemory(Path(tmp_path))
    memory.rebuild(
        [
            {
                "source": "agent_memory_assistant",
                "source_id": "memory-noise",
                "role": "assistant",
                "content": "conversation first routing note",
            },
            {
                "source": "knowledge_document",
                "source_id": "authoritative-doc",
                "role": "system",
                "content": "conversation first routing implementation contract",
                "metadata": {"path": "docs/trevor-interaction-contract.md"},
            },
        ]
    )

    result = memory.search("conversation first routing policy", top_k=1)

    assert result[0]["source"] == "knowledge_document"


def test_stale_knowledge_is_excluded_by_default_but_can_be_explicitly_included(tmp_path):
    from core.memory_layers import ThreeLayerMemory

    memory = ThreeLayerMemory(Path(tmp_path))
    memory.rebuild(
        [
            {
                "source": "knowledge_document",
                "source_id": "stale",
                "role": "system",
                "content": "data layer source of truth old architecture",
                "metadata": {"path": "DATA_LAYER_SOURCE_OF_TRUTH.md", "stale": True},
            },
            {
                "source": "knowledge_document",
                "source_id": "current",
                "role": "system",
                "content": "data layer source of truth current contract",
                "metadata": {"path": "docs/trevor-interaction-contract.md"},
            },
        ]
    )

    default_results = memory.search("data layer source of truth", top_k=5)
    historical_results = memory.search(
        "data layer source of truth", top_k=5, include_stale=True
    )

    assert all(not item["metadata"].get("stale") for item in default_results)
    assert any(item["metadata"].get("stale") for item in historical_results)
