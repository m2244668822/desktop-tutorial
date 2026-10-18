"""Print the idle worker readiness projection without changing local state."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from core.embedding_client import EmbeddingConfig
from core.idle_readiness import build_readiness_report
from tools.run_idle_embedding_worker import embedding_api_configured, external_embedding_allowed


def main() -> int:
    vault_root = Path(os.getenv("VAULT_WORKSPACE_ROOT", Path.cwd())).resolve()
    state_root = Path(
        os.getenv(
            "WHITE_STUDIO_EMBEDDING_STATE_DIR",
            vault_root / "runtime" / ".mcp-state" / "embedding-index",
        )
    ).resolve()
    config = EmbeddingConfig.from_env()
    report = build_readiness_report(
        state_root,
        model_id=config.model,
        vector_dimension=config.dimension,
    )
    report["runtime_gate"] = {
        "credential_present": embedding_api_configured(),
        "external_embedding_allowed": external_embedding_allowed(),
        "can_start_external_embedding": embedding_api_configured() and external_embedding_allowed(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
