from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from typing import Any, Protocol


class CredentialBackend(Protocol):
    def get(self, service: str, account: str) -> str | None: ...

    def set(self, service: str, account: str, value: str) -> None: ...

    def delete(self, service: str, account: str) -> None: ...


class MacOSKeychainBackend:
    def __init__(self):
        import Security

        self.security = Security

    def _query(self, service: str, account: str) -> dict[Any, Any]:
        security = self.security
        return {
            security.kSecClass: security.kSecClassGenericPassword,
            security.kSecAttrService: service,
            security.kSecAttrAccount: account,
        }

    def get(self, service: str, account: str) -> str | None:
        security = self.security
        query = {
            **self._query(service, account),
            security.kSecReturnData: True,
            security.kSecMatchLimit: security.kSecMatchLimitOne,
        }
        authentication_ui = getattr(security, "kSecUseAuthenticationUI", None)
        authentication_ui_fail = getattr(security, "kSecUseAuthenticationUIFail", None)
        if authentication_ui is not None and authentication_ui_fail is not None:
            query[authentication_ui] = authentication_ui_fail
        status, data = security.SecItemCopyMatching(query, None)
        if status == security.errSecItemNotFound:
            return None
        if status != security.errSecSuccess or data is None:
            raise RuntimeError("keychain_read_failed")
        return bytes(data).decode("utf-8")

    def set(self, service: str, account: str, value: str) -> None:
        security = self.security
        encoded = str(value).encode("utf-8")
        attributes = {
            **self._query(service, account),
            security.kSecValueData: encoded,
            security.kSecAttrAccessible: security.kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        }
        status, _ = security.SecItemAdd(attributes, None)
        if status == security.errSecDuplicateItem:
            status = security.SecItemUpdate(
                self._query(service, account),
                {security.kSecValueData: encoded},
            )
        if status != security.errSecSuccess:
            raise RuntimeError("keychain_write_failed")

    def delete(self, service: str, account: str) -> None:
        status = self.security.SecItemDelete(self._query(service, account))
        if status not in {self.security.errSecSuccess, self.security.errSecItemNotFound}:
            raise RuntimeError("keychain_delete_failed")


@dataclass(frozen=True)
class CredentialResult:
    configured: bool
    source: str
    value: str = field(default="", repr=False)
    error_code: str = ""

    def public_status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "configured": self.configured,
            "source": self.source,
        }
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload


class KeychainCredentialStore:
    def __init__(self, *, backend: CredentialBackend | None = None):
        self.backend = backend
        disabled = str(os.getenv("TREVOR_DISABLE_KEYCHAIN", "") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if self.backend is None and not disabled and platform.system() == "Darwin":
            try:
                self.backend = MacOSKeychainBackend()
            except Exception:
                self.backend = None

    def get_secret(self, service: str, account: str) -> CredentialResult:
        if self.backend is None:
            return CredentialResult(False, "keychain", error_code="credential_unavailable")
        try:
            value = str(self.backend.get(service, account) or "").strip()
        except Exception:
            return CredentialResult(False, "keychain", error_code="credential_unavailable")
        if not value:
            return CredentialResult(False, "keychain", error_code="credential_missing")
        return CredentialResult(True, "keychain", value=value)

    def set_secret(self, service: str, account: str, value: str) -> CredentialResult:
        if self.backend is None:
            return CredentialResult(False, "keychain", error_code="credential_unavailable")
        if not str(value or ""):
            return CredentialResult(False, "keychain", error_code="credential_missing")
        try:
            self.backend.set(service, account, str(value))
        except Exception:
            return CredentialResult(False, "keychain", error_code="credential_unavailable")
        return CredentialResult(True, "keychain", value=str(value))

    def delete_secret(self, service: str, account: str) -> bool:
        if self.backend is None:
            return False
        try:
            self.backend.delete(service, account)
        except Exception:
            return False
        return True


__all__ = [
    "CredentialResult",
    "KeychainCredentialStore",
    "MacOSKeychainBackend",
]
