from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest


KEY = b"s" * 32


def test_snapshot_round_trip_preserves_binary_files_and_manifest(tmp_path: Path) -> None:
    from tools.trevor_data_snapshot import create_snapshot, restore_snapshot

    source = tmp_path / "source"
    source.mkdir()
    (source / "nested").mkdir()
    (source / "notes.txt").write_text("Trevor", encoding="utf-8")
    binary = bytes(range(256)) * 32
    (source / "nested" / "index.bin").write_bytes(binary)
    snapshot = tmp_path / "backup.trevor.enc"
    manifest = tmp_path / "backup.manifest.json"
    restored = tmp_path / "restored"

    created = create_snapshot(source, snapshot, manifest, key_provider=lambda: KEY)
    result = restore_snapshot(snapshot, restored, manifest, key_provider=lambda: KEY)

    assert created["file_count"] == 2
    assert result["verified_files"] == 2
    assert (restored / "notes.txt").read_text(encoding="utf-8") == "Trevor"
    assert (restored / "nested" / "index.bin").read_bytes() == binary
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["algorithm"] == "AES-256-GCM"
    assert payload["file_count"] == 2
    assert payload["snapshot_sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_snapshot_excludes_transient_files(tmp_path: Path) -> None:
    from tools.trevor_data_snapshot import create_snapshot, restore_snapshot

    source = tmp_path / "source"
    source.mkdir()
    (source / "keep.json").write_text("{}", encoding="utf-8")
    (source / "ignore.lock").write_text("lock", encoding="utf-8")
    (source / "ignore.pid").write_text("123", encoding="utf-8")
    (source / "ignore.tmp").write_text("tmp", encoding="utf-8")
    (source / ".tmp-working").write_text("tmp", encoding="utf-8")
    snapshot = tmp_path / "backup.enc"
    manifest = tmp_path / "backup.json"
    restored = tmp_path / "restored"

    create_snapshot(source, snapshot, manifest, key_provider=lambda: KEY)
    result = restore_snapshot(snapshot, restored, manifest, key_provider=lambda: KEY)

    assert result["verified_files"] == 1
    assert (restored / "keep.json").exists()
    assert not (restored / "ignore.lock").exists()
    assert not (restored / "ignore.pid").exists()
    assert not (restored / "ignore.tmp").exists()
    assert not (restored / ".tmp-working").exists()


def test_tampered_ciphertext_fails_closed(tmp_path: Path) -> None:
    from tools.trevor_data_snapshot import SnapshotError, create_snapshot, restore_snapshot

    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("secret", encoding="utf-8")
    snapshot = tmp_path / "backup.enc"
    manifest = tmp_path / "backup.json"
    create_snapshot(source, snapshot, manifest, key_provider=lambda: KEY)
    tampered = bytearray(snapshot.read_bytes())
    tampered[-1] ^= 1
    snapshot.write_bytes(tampered)

    with pytest.raises(SnapshotError):
        restore_snapshot(snapshot, tmp_path / "restored", manifest, key_provider=lambda: KEY)


def test_tampered_manifest_fails_closed(tmp_path: Path) -> None:
    from tools.trevor_data_snapshot import SnapshotError, create_snapshot, restore_snapshot

    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("secret", encoding="utf-8")
    snapshot = tmp_path / "backup.enc"
    manifest = tmp_path / "backup.json"
    create_snapshot(source, snapshot, manifest, key_provider=lambda: KEY)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["files"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SnapshotError):
        restore_snapshot(snapshot, tmp_path / "restored", manifest, key_provider=lambda: KEY)


def test_restore_rejects_path_traversal() -> None:
    from tools.trevor_data_snapshot import SnapshotError, safe_extract_tar

    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        info = tarfile.TarInfo("../outside.txt")
        content = b"nope"
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    stream.seek(0)

    with pytest.raises(SnapshotError):
        safe_extract_tar(stream, Path("C:/isolated"))


def test_source_is_unchanged_by_snapshot(tmp_path: Path) -> None:
    from tools.trevor_data_snapshot import create_snapshot

    source = tmp_path / "source"
    source.mkdir()
    file_path = source / "file.txt"
    file_path.write_text("unchanged", encoding="utf-8")
    before = (file_path.stat().st_mtime_ns, file_path.read_bytes())

    create_snapshot(source, tmp_path / "backup.enc", tmp_path / "backup.json", key_provider=lambda: KEY)

    after = (file_path.stat().st_mtime_ns, file_path.read_bytes())
    assert after == before


def test_verify_snapshot_checks_external_manifest(tmp_path: Path) -> None:
    from tools.trevor_data_snapshot import create_snapshot, verify_snapshot

    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("verified", encoding="utf-8")
    snapshot = tmp_path / "backup.enc"
    manifest = tmp_path / "backup.json"
    create_snapshot(source, snapshot, manifest, key_provider=lambda: KEY)

    result = verify_snapshot(snapshot, manifest, key_provider=lambda: KEY)

    assert result["verified_files"] == 1
    assert result["snapshot_sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
