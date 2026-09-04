#!/usr/bin/env python3
"""Configure Trevor's AI Horde key without exposing it in argv or source files."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.keychain_credentials import KeychainCredentialStore


SERVICE = "perob.ai-horde"
ACCOUNT = "api-key"
ANONYMOUS_KEY = "0000000000"


def credential_status(store: KeychainCredentialStore) -> dict[str, object]:
    result = store.get_secret(SERVICE, ACCOUNT)
    return {
        "ok": True,
        "configured": result.configured,
        "source": result.source,
        "error_code": result.error_code,
        "service": SERVICE,
        "account": ACCOUNT,
    }


def configure(store: KeychainCredentialStore) -> dict[str, object]:
    secret = getpass.getpass("AI Horde API key（輸入不會顯示）: ").strip()
    if not secret:
        raise RuntimeError("credential_missing")
    saved = store.set_secret(SERVICE, ACCOUNT, secret)
    if not saved.configured:
        raise RuntimeError(saved.error_code or "credential_write_failed")
    verified = store.get_secret(SERVICE, ACCOUNT)
    if not verified.configured or verified.value != secret:
        raise RuntimeError("credential_verification_failed")
    return {
        "ok": True,
        "configured": True,
        "source": verified.source,
        "service": SERVICE,
        "account": ACCOUNT,
    }


def configure_anonymous(store: KeychainCredentialStore) -> dict[str, object]:
    saved = store.set_secret(SERVICE, ACCOUNT, ANONYMOUS_KEY)
    if not saved.configured:
        raise RuntimeError(saved.error_code or "credential_write_failed")
    return {
        "ok": True,
        "configured": True,
        "anonymous": True,
        "priority": "lowest",
        "source": saved.source,
        "service": SERVICE,
        "account": ACCOUNT,
    }


def delete(store: KeychainCredentialStore, *, confirmed: bool) -> dict[str, object]:
    if not confirmed:
        raise RuntimeError("delete_requires_yes")
    deleted = store.delete_secret(SERVICE, ACCOUNT)
    return {"ok": deleted, "configured": False, "deleted": deleted}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Store the AI Horde key in the operating system credential manager."
    )
    parser.add_argument(
        "action",
        choices=("status", "set", "anonymous", "delete"),
        nargs="?",
        default="status",
    )
    parser.add_argument("--yes", action="store_true", help="Confirm credential deletion")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    store = KeychainCredentialStore()
    try:
        if args.action == "set":
            result = configure(store)
        elif args.action == "anonymous":
            result = configure_anonymous(store)
        elif args.action == "delete":
            result = delete(store, confirmed=bool(args.yes))
        else:
            result = credential_status(store)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
