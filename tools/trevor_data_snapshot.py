#!/usr/bin/env python3
"""Create and verify encrypted TrevorData snapshots.

The snapshot format intentionally keeps the device key outside the archive.  The
archive contains a canonical manifest so an external manifest can be checked for
tampering before any restored directory is promoted.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import secrets
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Callable, Iterable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.encrypted_store import DeviceEncryptionKey


MAGIC = b"TREVOR-SNAPSHOT-V1\n"
AAD = b"trevor-data-snapshot-v1"
INTERNAL_MANIFEST = ".trevor_snapshot_manifest.json"
KEY_LENGTH = 32
NONCE_LENGTH = 12
TRANSIENT_SUFFIXES = (".lock", ".pid", ".tmp")


class SnapshotError(RuntimeError):
    """Raised when a snapshot cannot be safely created or verified."""


KeyProvider = Callable[[], bytes]


def _default_key_provider() -> bytes:
    return DeviceEncryptionKey(
        service="trevor.snapshot",
        account="aes-256-gcm",
    ).get_or_create()


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_key(key_provider: KeyProvider) -> bytes:
    key = bytes(key_provider())
    if len(key) != KEY_LENGTH:
        raise SnapshotError("AES-256-GCM requires a 32-byte key")
    return key


def _is_transient(path: Path) -> bool:
    name = path.name
    return (
        name.startswith(".tmp")
        or name.endswith(TRANSIENT_SUFFIXES)
        or name.endswith("~")
    )


def _iter_source_files(source: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    excluded: list[str] = []
    for candidate in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        relative = candidate.relative_to(source).as_posix()
        if _is_transient(candidate):
            excluded.append(relative)
            continue
        if candidate.is_symlink():
            excluded.append(relative)
            continue
        if candidate.is_file():
            files.append(candidate)
    return files, excluded


def _file_entries(source: Path, files: Iterable[Path]) -> list[dict[str, object]]:
    entries = []
    for path in files:
        stat = path.stat()
        entries.append(
            {
                "path": path.relative_to(source).as_posix(),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": _sha256_file(path),
            }
        )
    return entries


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{secrets.token_hex(8)}")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: object) -> None:
    _atomic_write(path, _canonical_json(payload))


def _assert_distinct_paths(source: Path, output: Path, manifest: Path) -> None:
    source_resolved = source.resolve()
    for target in (output.resolve(), manifest.resolve()):
        if target == source_resolved or source_resolved in target.parents:
            raise SnapshotError("snapshot artifacts must be outside source directory")
    if output.resolve() == manifest.resolve():
        raise SnapshotError("snapshot and manifest paths must differ")


def _build_archive(source: Path, core_manifest: dict[str, object]) -> bytes:
    with tempfile.TemporaryDirectory(prefix="trevor-snapshot-") as temporary_dir:
        archive_path = Path(temporary_dir) / "payload.tar.gz"
        with tarfile.open(archive_path, mode="w:gz") as archive:
            for entry in core_manifest["files"]:
                path = source / str(entry["path"])
                archive.add(path, arcname=str(entry["path"]), recursive=False)
            encoded_manifest = _canonical_json(core_manifest)
            info = tarfile.TarInfo(INTERNAL_MANIFEST)
            info.size = len(encoded_manifest)
            info.mode = 0o600
            info.mtime = 0
            archive.addfile(info, io.BytesIO(encoded_manifest))
        return archive_path.read_bytes()


def _write_encrypted_snapshot(output: Path, archive_bytes: bytes, key: bytes, manifest_hash: str) -> None:
    nonce = secrets.token_bytes(NONCE_LENGTH)
    ciphertext = AESGCM(key).encrypt(nonce, archive_bytes, AAD)
    header = {
        "version": 1,
        "algorithm": "AES-256-GCM",
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "aad": base64.b64encode(AAD).decode("ascii"),
        "archive_size": len(archive_bytes),
        "archive_sha256": _sha256_bytes(archive_bytes),
        "manifest_sha256": manifest_hash,
    }
    _atomic_write(output, MAGIC + _canonical_json(header) + ciphertext)


def _read_encrypted_snapshot(snapshot: Path, key: bytes) -> tuple[dict[str, object], bytes]:
    try:
        with snapshot.open("rb") as handle:
            if handle.readline() != MAGIC:
                raise SnapshotError("invalid snapshot magic")
            header_line = handle.readline()
            header = json.loads(header_line.decode("utf-8"))
            ciphertext = handle.read()
        if not isinstance(header, dict) or header.get("algorithm") != "AES-256-GCM":
            raise SnapshotError("invalid snapshot header")
        nonce = base64.b64decode(str(header["nonce"]), validate=True)
        aad = base64.b64decode(str(header["aad"]), validate=True)
        if aad != AAD or len(nonce) != NONCE_LENGTH:
            raise SnapshotError("invalid snapshot envelope")
        archive_bytes = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, InvalidTag) as exc:
        raise SnapshotError("snapshot authentication failed") from exc
    if len(archive_bytes) != int(header.get("archive_size", -1)):
        raise SnapshotError("snapshot archive size mismatch")
    if _sha256_bytes(archive_bytes) != str(header.get("archive_sha256", "")):
        raise SnapshotError("snapshot archive checksum mismatch")
    return header, archive_bytes


def _safe_member_path(destination: Path, name: str) -> Path:
    if not name or Path(name).is_absolute():
        raise SnapshotError("absolute archive member path rejected")
    target = (destination / Path(name)).resolve()
    if target != destination.resolve() and not target.is_relative_to(destination.resolve()):
        raise SnapshotError("archive path traversal rejected")
    return target


def safe_extract_tar(stream: BinaryIO, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=stream, mode="r:gz") as archive:
        for member in archive.getmembers():
            target = _safe_member_path(destination, member.name)
            if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise SnapshotError("unsupported archive member type")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise SnapshotError("archive member could not be read")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError("manifest unreadable") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise SnapshotError("manifest invalid")
    return payload


def _verify_restored_files(destination: Path, manifest: dict[str, object]) -> int:
    verified = 0
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise SnapshotError("manifest file entry invalid")
        relative = str(entry.get("path", ""))
        target = _safe_member_path(destination, relative)
        if not target.is_file():
            raise SnapshotError(f"restored file missing: {relative}")
        if target.stat().st_size != int(entry.get("size", -1)):
            raise SnapshotError(f"restored file size mismatch: {relative}")
        if _sha256_file(target) != str(entry.get("sha256", "")):
            raise SnapshotError(f"restored file checksum mismatch: {relative}")
        verified += 1
    return verified


def _manifest_core(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": manifest.get("schema_version"),
        "source_root": manifest.get("source_root"),
        "created_at": manifest.get("created_at"),
        "excluded": manifest.get("excluded", []),
        "files": manifest.get("files", []),
    }


def create_snapshot(
    source: Path,
    output: Path,
    manifest: Path,
    *,
    key_provider: KeyProvider = _default_key_provider,
) -> dict[str, object]:
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    manifest = Path(manifest).expanduser().resolve()
    if not source.is_dir():
        raise SnapshotError("source directory does not exist")
    _assert_distinct_paths(source, output, manifest)
    files, excluded = _iter_source_files(source)
    core = {
        "schema_version": 1,
        "source_root": str(source),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "excluded": excluded,
        "files": _file_entries(source, files),
    }
    core_hash = _sha256_bytes(_canonical_json(core))
    archive_bytes = _build_archive(source, core)
    key = _validate_key(key_provider)
    _write_encrypted_snapshot(output, archive_bytes, key, core_hash)
    snapshot_hash = _sha256_file(output)
    external = {
        **core,
        "algorithm": "AES-256-GCM",
        "file_count": len(files),
        "archive_size": len(archive_bytes),
        "archive_sha256": _sha256_bytes(archive_bytes),
        "manifest_sha256": core_hash,
        "snapshot_size": output.stat().st_size,
        "snapshot_sha256": snapshot_hash,
    }
    _atomic_write_json(manifest, external)
    return {"file_count": len(files), "snapshot_sha256": snapshot_hash, "manifest": str(manifest)}


def _verify_archive_against_manifest(archive_bytes: bytes, external: dict[str, object], destination: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="trevor-restore-verify-") as temporary_dir:
        staging = Path(temporary_dir) / "payload"
        safe_extract_tar(io.BytesIO(archive_bytes), staging)
        internal_path = staging / INTERNAL_MANIFEST
        internal = _load_manifest(internal_path)
        if _sha256_bytes(_canonical_json(_manifest_core(internal))) != str(external.get("manifest_sha256", "")):
            raise SnapshotError("manifest authentication mismatch")
        if _manifest_core(internal) != _manifest_core(external):
            raise SnapshotError("external manifest does not match encrypted manifest")
        if destination:
            return _verify_restored_files(staging, external)
        return len(external["files"])


def verify_snapshot(
    snapshot: Path,
    manifest: Path,
    *,
    key_provider: KeyProvider = _default_key_provider,
) -> dict[str, object]:
    snapshot = Path(snapshot).expanduser().resolve()
    manifest_payload = _load_manifest(Path(manifest).expanduser().resolve())
    actual_snapshot_hash = _sha256_file(snapshot)
    if actual_snapshot_hash != str(manifest_payload.get("snapshot_sha256", "")):
        raise SnapshotError("snapshot checksum mismatch")
    header, archive_bytes = _read_encrypted_snapshot(snapshot, _validate_key(key_provider))
    if str(header.get("manifest_sha256", "")) != str(manifest_payload.get("manifest_sha256", "")):
        raise SnapshotError("snapshot manifest digest mismatch")
    verified = _verify_archive_against_manifest(archive_bytes, manifest_payload, Path())
    return {"verified_files": verified, "snapshot_sha256": actual_snapshot_hash}


def restore_snapshot(
    snapshot: Path,
    destination: Path,
    manifest: Path,
    *,
    key_provider: KeyProvider = _default_key_provider,
) -> dict[str, object]:
    snapshot = Path(snapshot).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    manifest_path = Path(manifest).expanduser().resolve()
    if destination.exists():
        raise SnapshotError("restore destination must not already exist")
    manifest_payload = _load_manifest(manifest_path)
    actual_snapshot_hash = _sha256_file(snapshot)
    if actual_snapshot_hash != str(manifest_payload.get("snapshot_sha256", "")):
        raise SnapshotError("snapshot checksum mismatch")
    header, archive_bytes = _read_encrypted_snapshot(snapshot, _validate_key(key_provider))
    if str(header.get("manifest_sha256", "")) != str(manifest_payload.get("manifest_sha256", "")):
        raise SnapshotError("snapshot manifest digest mismatch")
    staging = destination.with_name(f".{destination.name}.tmp-{secrets.token_hex(8)}")
    try:
        staging.mkdir(parents=True)
        safe_extract_tar(io.BytesIO(archive_bytes), staging)
        internal_path = staging / INTERNAL_MANIFEST
        internal = _load_manifest(internal_path)
        if _sha256_bytes(_canonical_json(_manifest_core(internal))) != str(manifest_payload.get("manifest_sha256", "")):
            raise SnapshotError("manifest authentication mismatch")
        if _manifest_core(internal) != _manifest_core(manifest_payload):
            raise SnapshotError("external manifest does not match encrypted manifest")
        verified = _verify_restored_files(staging, manifest_payload)
        internal_path.unlink()
        staging.replace(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"verified_files": verified, "destination": str(destination), "snapshot_sha256": actual_snapshot_hash}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--source", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--manifest", type=Path, required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--snapshot", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    restore.add_argument("--manifest", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--snapshot", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_snapshot(args.source, args.output, args.manifest)
        elif args.command == "restore":
            result = restore_snapshot(args.snapshot, args.destination, args.manifest)
        else:
            result = verify_snapshot(args.snapshot, args.manifest)
    except SnapshotError as exc:
        print(f"snapshot_error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
