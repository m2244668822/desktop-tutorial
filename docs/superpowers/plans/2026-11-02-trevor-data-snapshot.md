# TrevorData Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a reproducible AES-256-GCM TrevorData snapshot with a checksum manifest and isolated restore verification.

**Architecture:** Add a focused CLI under `tools/` that archives the source tree with deterministic filtering, encrypts the compressed archive with the existing Trevor device key, and emits a canonical manifest. A restore command decrypts into a caller-provided isolated directory and validates every manifest entry without modifying the source.

**Tech Stack:** Python 3.12, `tarfile`, `hashlib`, `json`, `cryptography.hazmat.primitives.ciphers.aead.AESGCM`, existing `core.encrypted_store.DeviceEncryptionKey`.

**Spec:** `docs/superpowers/specs/2026-11-02-trevor-data-snapshot-design.md`

## Global Constraints

- Never modify, delete, or move files under the source `TrevorData` directory.
- Never print or write the raw encryption key.
- Use AES-256-GCM with a fresh 12-byte nonce per snapshot.
- Exclude lock, pid, and temporary files from the snapshot.
- Write final artifacts atomically from temporary files.

## Review Focus

- Binary files must round-trip byte-for-byte, not through text decoding.
- Path traversal in archive members must be rejected during restore.
- Tampered ciphertext and tampered manifest must fail closed.
- Empty and nested source directories must produce a valid manifest.
- A failed snapshot must not leave a misleading final artifact.

### Task 1: Snapshot CLI and verification tests

**Files:**
- Create: `tools/trevor_data_snapshot.py`
- Create: `tests/test_trevor_data_snapshot.py`
- Modify: none outside the new files

**Interfaces:**
- `create_snapshot(source: Path, output: Path, manifest: Path) -> dict`
- `restore_snapshot(snapshot: Path, destination: Path, manifest: Path) -> dict`
- CLI subcommands `create`, `restore`, and `verify`.

- [ ] **Step 1: Write failing tests** for successful round-trip, binary data, excluded transient files, tampered ciphertext, tampered manifest, path traversal rejection, and source immutability.
- [ ] **Step 2: Run the focused test file and verify it fails because the CLI module is missing.
- [ ] **Step 3: Implement the minimal CLI and AES-256-GCM envelope.
- [ ] **Step 4: Run the focused tests and verify all pass.
- [ ] **Step 5: Run the full project suite `pytest -q` and record the result.
- [ ] **Step 6: Run the real P0 create/restore verification against `E:\智能體\TrevorData` into an isolated temporary destination.

