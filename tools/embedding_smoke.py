"""Live NVIDIA embedding smoke test. Never prints credentials or vectors."""

from __future__ import annotations

import json
import os

from core.embedding_client import EmbeddingConfig, NemotronEmbeddingClient


def main() -> int:
    client = NemotronEmbeddingClient()
    query = client.embed_one("White Studio MCP Orchestrator", input_type="query")
    passage = client.embed_one("White Studio MCP Orchestrator", input_type="passage")
    print(
        json.dumps(
            {
                "status": "EMBEDDING_API_PASS",
                "provider": "nvidia",
                "model": client.config.model,
                "base_url": client.config.base_url,
                "query_dimension": len(query),
                "passage_dimension": len(passage),
                "api_key_present": bool(os.getenv("NVIDIA_API_KEY")),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
