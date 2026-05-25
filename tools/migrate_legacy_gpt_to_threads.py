#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from core.data_paths import resolve_data_root


def sig(user: str, assistant: str) -> str:
    raw = f"{(user or '').strip()}\n---\n{(assistant or '').strip()}"
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=16).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy GPT chats into thread-style conversations.json")
    parser.add_argument("--workspace", default="", help="Workspace root (default: repo root)")
    parser.add_argument(
        "--legacy",
        default="500/llama32-chat/data/conversations.json",
        help="Legacy conversations path (relative to workspace unless absolute)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if args.workspace
        else Path(__file__).resolve().parents[1]
    )
    data_root = resolve_data_root(workspace)

    target = data_root / "agent_memories" / "conversations.json"
    legacy = Path(args.legacy).expanduser()
    if not legacy.is_absolute():
        legacy = workspace / legacy

    backup_dir = data_root / "agent_memories" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not legacy.exists():
        print(f"legacy not found: {legacy}")
        return 1

    if target.exists():
        threads = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(threads, dict):
            print("target conversations is not dict")
            return 2
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        threads = {}

    legacy_rows = json.loads(legacy.read_text(encoding="utf-8"))
    if not isinstance(legacy_rows, list):
        print("legacy conversations is not list")
        return 2

    backup_file = backup_dir / (
        f"conversations_before_full_legacy_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    backup_file.write_text(
        json.dumps(threads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    existing = set()
    for conv in threads.values():
        if not isinstance(conv, dict):
            continue
        for item in conv.get("messages", []):
            existing.add(sig(str(item.get("user", "")), str(item.get("assistant", ""))))

    added = 0
    skipped_empty = 0
    skipped_dup = 0

    for idx, row in enumerate(legacy_rows):
        if not isinstance(row, dict):
            continue
        user = str(row.get("prompt", "")).strip()
        assistant = str(row.get("response", "")).strip()
        if not user and not assistant:
            skipped_empty += 1
            continue

        digest = sig(user, assistant)
        if digest in existing:
            skipped_dup += 1
            continue

        ts = str(row.get("timestamp", "")).strip() or datetime.now().isoformat()
        cid = f"legacy-full-{idx:06d}"
        if cid in threads:
            cid = f"legacy-full-{idx:06d}-{hashlib.md5(ts.encode('utf-8')).hexdigest()[:6]}"

        threads[cid] = {
            "agent_name": "legacy_import",
            "created_at": ts,
            "last_message_at": ts,
            "messages": [
                {
                    "timestamp": ts,
                    "user": user,
                    "assistant": assistant,
                    "metadata": {
                        "source": "legacy_llama32_chat_full_import",
                        "model": row.get("model", ""),
                        "status": row.get("status", ""),
                    },
                }
            ],
        }
        existing.add(digest)
        added += 1

    target.write_text(json.dumps(threads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "workspace": str(workspace),
                "data_root": str(data_root),
                "legacy_rows": len(legacy_rows),
                "threads_total": len(threads),
                "added": added,
                "skipped_dup": skipped_dup,
                "skipped_empty": skipped_empty,
                "backup": str(backup_file),
                "target": str(target),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
