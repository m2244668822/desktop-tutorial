#!/usr/bin/env python3
"""Detect case-insensitive filename collisions in a directory tree.

Useful before moving projects from case-sensitive volumes (some SSD setups)
to case-insensitive targets (common HDD / Windows NTFS).
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path


def find_collisions(base: Path) -> list[dict]:
    collisions: list[dict] = []
    for root, dirs, files in os.walk(base):
        bucket: dict[str, list[str]] = defaultdict(list)
        for name in dirs + files:
            bucket[name.casefold()].append(name)
        clash = [sorted(v) for v in bucket.values() if len(v) > 1]
        if clash:
            collisions.append(
                {
                    "path": str(Path(root)),
                    "collisions": clash,
                }
            )
    return collisions


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect case-insensitive collisions")
    parser.add_argument("path", nargs="?", default=".", help="Folder to scan")
    parser.add_argument("--json-out", help="Optional JSON report output path")
    args = parser.parse_args()

    base = Path(args.path).resolve()
    if not base.exists():
        print(f"ERROR: path not found: {base}")
        return 2

    result = find_collisions(base)
    summary = {
        "base": str(base),
        "collision_dirs": len(result),
        "items": result,
    }

    if args.json_out:
        out = Path(args.json_out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report written: {out}")

    if not result:
        print("OK: no case-insensitive collisions found.")
        return 0

    print(f"WARNING: found {len(result)} directories with collisions")
    for entry in result[:20]:
        print(f"- {entry['path']}")
        for group in entry["collisions"]:
            print(f"  * {'  |  '.join(group)}")
    if len(result) > 20:
        print(f"... and {len(result) - 20} more directories")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

