#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api_auth import CLIENT_SERVICE, LOCAL_ADMIN_ACCOUNT
from core.audit_chain import HashChainAuditLog
from core.data_paths import resolve_data_root
from core.keychain_credentials import KeychainCredentialStore


Runner = Callable[..., subprocess.CompletedProcess[str]]
REMOTE_HOST_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+$")


def bootstrap_remote_admin(
    remote_host: str,
    *,
    ssh_key: str | Path,
    credential_store: KeychainCredentialStore | Any | None = None,
    runner: Runner = subprocess.run,
    remote_app_root: str = "/opt/trevor/app",
    remote_data_root: str = "/var/lib/trevor",
    remote_credentials_directory: str = "/etc/trevor/credentials",
) -> dict[str, Any]:
    host = str(remote_host or "").strip()
    if not REMOTE_HOST_PATTERN.fullmatch(host):
        raise RuntimeError("invalid_remote_host")
    key_path = Path(ssh_key).expanduser().resolve()
    if not key_path.is_file():
        raise RuntimeError("ssh_key_unavailable")
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-i",
        str(key_path),
        host,
        "sudo",
        "-n",
        f"{remote_app_root}/.venv/bin/python",
        f"{remote_app_root}/tools/issue_trevor_api_key.py",
        "--data-root",
        remote_data_root,
        "--credentials-directory",
        remote_credentials_directory,
        "--label",
        "mac-edge",
        "--scope",
        "chat",
        "--scope",
        "memory",
        "--scope",
        "tasks",
    ]
    process = runner(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if process.returncode != 0:
        raise RuntimeError("remote_api_key_issue_failed")
    try:
        payload = json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError("remote_api_key_response_invalid") from exc
    api_key = str(payload.get("api_key", "") or "").strip()
    record = payload.get("record")
    if not api_key.startswith("trv_") or not isinstance(record, dict):
        raise RuntimeError("remote_api_key_response_invalid")
    store = credential_store or KeychainCredentialStore()
    saved = store.set_secret(CLIENT_SERVICE, LOCAL_ADMIN_ACCOUNT, api_key)
    if not saved.configured:
        raise RuntimeError("local_admin_keychain_unavailable")
    return {
        "ok": True,
        "created": True,
        "remote_host": host,
        "key_id": str(record.get("id", "") or ""),
        "prefix": str(record.get("prefix", "") or ""),
        "scopes": list(record.get("scopes", [])),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Issue an OCI Trevor API key and save it to the Mac Keychain"
    )
    parser.add_argument(
        "--remote-host",
        default=os.getenv("TREVOR_OCI_SSH_HOST", ""),
        required=not bool(os.getenv("TREVOR_OCI_SSH_HOST", "").strip()),
    )
    parser.add_argument(
        "--ssh-key",
        default=str(Path.home() / ".ssh" / "trevor_oci_ed25519"),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = bootstrap_remote_admin(
            args.remote_host,
            ssh_key=args.ssh_key,
        )
        HashChainAuditLog(
            resolve_data_root(ROOT) / "audit" / "events.jsonl"
        ).append(
            "user_key_bootstrap",
            {
                "key_id": result["key_id"],
                "prefix": result["prefix"],
                "scopes": result["scopes"],
                "remote_host": result["remote_host"],
            },
        )
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
