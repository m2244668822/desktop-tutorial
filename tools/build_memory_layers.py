#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建立三層記憶的 SQLite + FAISS 長期記憶層。
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.memory_layers import ThreeLayerMemory, collect_memory_sources


def main() -> int:
    memory = ThreeLayerMemory(BASE_DIR)
    sources = collect_memory_sources(BASE_DIR)
    result = memory.rebuild(sources)

    print("✅ 三層記憶已重建")
    print(f"   items: {result['items_indexed']}")
    dedupe = result.get("dedupe", {})
    if dedupe:
        print(
            "   dedupe:"
            f" input={dedupe.get('input_items', 0)}"
            f" exact_removed={dedupe.get('exact_duplicates_removed', 0)}"
            f" kept={dedupe.get('deduped_items', 0)}"
        )
    print(f"   sqlite: {result['sqlite_path']}")
    print(f"   faiss: {result['faiss_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
