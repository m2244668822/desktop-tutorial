#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:
    import pwd
except ImportError:
    pwd = None


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api_auth import build_api_key_store
from core.audit_chain import HashChainAuditLog


PrivilegeDropper = Callable[[str, Path], None]


def drop_to_service_user(user_name: str, data_root: Path) -> None:
    name = str(user_name or "").strip()
    if not name:
        return
    if pwd is None:
        raise RuntimeError("service_user_switch_unsupported")
    try:
        account = pwd.getpwnam(name)
    except KeyError as exc:
        raise RuntimeError("service_user_unavailable") from exc
    current_uid = os.geteuid()
    if current_uid == account.pw_uid:
        return
    if current_uid != 0:
        raise RuntimeError("service_user_switch_requires_root")
    if not data_root.is_dir():
        raise RuntimeError("service_data_root_unavailable")
    try:
        os.initgroups(name, account.pw_gid)
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    except OSError as exc:
        raise RuntimeError("service_user_switch_failed") from exc
    if os.geteuid() != account.pw_uid:
        raise RuntimeError("service_user_switch_failed")


def issue_api_key(
    data_root: str | Path,
    credentials_directory: str | Path,
    *,
    label: str,
    scopes: Iterable[str],
    service_user: str = "",
    privilege_dropper: PrivilegeDropper = drop_to_service_user,
) -> dict:
    root = Path(data_root).expanduser().resolve()
    key_store, status = build_api_key_store(
        root,
        credentials_directory=credentials_directory,
    )
    if key_store is None:
        raise RuntimeError("api_hmac_unavailable")
    if str(service_user or "").strip():
        privilege_dropper(str(service_user).strip(), root)
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
    parser.add_argument("--service-user", default="trevor")
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
            service_user=args.service_user,
        )
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
