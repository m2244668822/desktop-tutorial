#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data_migration import TrevorDataMigrator
from core.data_paths import default_trevor_data_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--destination", type=Path, default=default_trevor_data_dir())
    args = parser.parse_args()
    result = TrevorDataMigrator(args.workspace, args.destination).migrate()
    print(
        json.dumps(
            {
                "ok": True,
                "unique_turns": result["unique_turns"],
                "conversation_threads": result["conversation_threads"],
                "copied_files": result["copied_files"],
                "destination": str(args.destination.expanduser().resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
