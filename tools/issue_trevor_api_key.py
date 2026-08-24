#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api_auth import build_api_key_store
from core.audit_chain import HashChainAuditLog


def issue_api_key(
    data_root: str | Path,
    credentials_directory: str | Path,
    *,
    label: str,
    scopes: Iterable[str],
) -> dict:
    root = Path(data_root).expanduser().resolve()
    key_store, status = build_api_key_store(
        root,
        credentials_directory=credentials_directory,
    )
    if key_store is None:
        raise RuntimeError("api_hmac_unavailable")
    created = key_store.create(label, scopes)
    HashChainAuditLog(root / "audit" / "events.jsonl").append(
        "user_key_bootstrap",
        {
            "key_id": created["record"]["id"],
            "prefix": created["record"]["prefix"],
            "scopes": created["record"]["scopes"],
            "source": status["source"],
        },
    )
    return {"ok": True, **created}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue a Trevor API key on the API host")
    parser.add_argument("--data-root", default="/var/lib/trevor")
    parser.add_argument(
        "--credentials-directory", default="/etc/trevor/credentials"
    )
    parser.add_argument("--label", default="mac-edge")
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        choices=("chat", "memory", "tasks", "git", "users", "audit"),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = issue_api_key(
            args.data_root,
            args.credentials_directory,
            label=args.label,
            scopes=args.scopes or ("chat", "memory", "tasks"),
        )
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
