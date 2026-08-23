from __future__ import annotations

import base64
import json
import os
import secrets
from pathlib import Path
from typing import Any, Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.keychain_credentials import KeychainCredentialStore


class EncryptedStoreError(RuntimeError):
    pass


class DeviceEncryptionKey:
    def __init__(
        self,
        credential_store: KeychainCredentialStore | None = None,
        *,
        service: str = "trevor.memory",
        account: str = "aes-256-gcm",
        credentials_directory: str | os.PathLike[str] | None = None,
    ):
        self.credential_store = credential_store or KeychainCredentialStore()
        self.service = service
        self.account = account
        self.credentials_directory = (
            Path(credentials_directory).expanduser()
            if credentials_directory is not None
            else None
        )

    def get_or_create(self) -> bytes:
        directory = self.credentials_directory
        if directory is None:
            configured_directory = os.getenv("CREDENTIALS_DIRECTORY", "").strip()
            directory = Path(configured_directory) if configured_directory else None
        if directory is not None:
            try:
                systemd_value = (directory / "trevor_memory_key_b64").read_text(
                    encoding="utf-8"
                ).strip()
            except OSError:
                systemd_value = ""
            if systemd_value:
                return self._decode(systemd_value)
        configured = os.getenv("TREVOR_MEMORY_KEY_B64", "").strip()
        if configured:
            return self._decode(configured)
        result = self.credential_store.get_secret(self.service, self.account)
        if result.configured:
            return self._decode(result.value)
        key = secrets.token_bytes(32)
        encoded = base64.b64encode(key).decode("ascii")
        stored = self.credential_store.set_secret(self.service, self.account, encoded)
        if not stored.configured:
            raise EncryptedStoreError("device_encryption_key_unavailable")
        return key

    @staticmethod
    def _decode(value: str) -> bytes:
        try:
            key = base64.b64decode(value, validate=True)
        except ValueError as exc:
            raise EncryptedStoreError("invalid_device_encryption_key") from exc
        if len(key) != 32:
            raise EncryptedStoreError("invalid_device_encryption_key")
        return key


class AESGCMJsonStore:
    AAD = b"trevor-json-store-v1"

    def __init__(self, key_provider: Callable[[], bytes]):
        self.key_provider = key_provider

    def _key(self) -> bytes:
        key = bytes(self.key_provider())
        if len(key) != 32:
            raise EncryptedStoreError("AES-256-GCM requires a 32-byte key")
        return key

    @staticmethod
    def _load_envelope(path: Path) -> Any:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EncryptedStoreError("encrypted_store_read_failed") from exc
        return payload

    def is_encrypted(self, path: str | Path) -> bool:
        target = Path(path)
        if not target.exists():
            return False
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return bool(
            isinstance(payload, dict)
            and payload.get("algorithm") == "AES-256-GCM"
            and payload.get("version") == 1
        )

    def read_json(self, path: str | Path, default: Any) -> Any:
        target = Path(path)
        if not target.exists():
            return default
        envelope = self._load_envelope(target)
        if not isinstance(envelope, dict) or envelope.get("algorithm") != "AES-256-GCM":
            return envelope
        try:
            nonce = base64.b64decode(str(envelope["nonce"]), validate=True)
            ciphertext = base64.b64decode(str(envelope["ciphertext"]), validate=True)
            plaintext = AESGCM(self._key()).decrypt(nonce, ciphertext, self.AAD)
            return json.loads(plaintext.decode("utf-8"))
        except (KeyError, ValueError, InvalidTag, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EncryptedStoreError("encrypted_store_authentication_failed") from exc

    def write_json(self, path: str | Path, payload: Any) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(self._key()).encrypt(nonce, plaintext, self.AAD)
        envelope = {
            "version": 1,
            "algorithm": "AES-256-GCM",
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(envelope, ensure_ascii=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)

    def reencrypt_json(self, path: str | Path) -> None:
        target = Path(path)
        payload = self.read_json(target, {})
        self.write_json(target, payload)


__all__ = ["AESGCMJsonStore", "DeviceEncryptionKey", "EncryptedStoreError"]
