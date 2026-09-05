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
        self.authentication_context_factory = self._load_authentication_context_factory()

    @staticmethod
    def _load_authentication_context_factory():
        try:
            import objc
            from Foundation import NSBundle

            bundle = NSBundle.bundleWithPath_(
                "/System/Library/Frameworks/LocalAuthentication.framework"
            )
            if bundle is None or not bundle.load():
                return None
            context_class = objc.lookUpClass("LAContext")
        except Exception:
            return None
        return lambda: context_class.alloc().init()

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
        no_authentication_ui = getattr(security, "kSecUseNoAuthenticationUI", None)
        if no_authentication_ui is not None:
            query[no_authentication_ui] = True
        authentication_context_key = getattr(
            security, "kSecUseAuthenticationContext", None
        )
        context_factory = getattr(self, "authentication_context_factory", None)
        if authentication_context_key is not None and callable(context_factory):
            context = context_factory()
            context.setInteractionNotAllowed_(True)
            query[authentication_context_key] = context
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


class WindowsCredentialManagerBackend:
    """Store generic credentials through the Windows Credential Manager API."""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)

    @staticmethod
    def _target(service: str, account: str) -> str:
        return f"{service}/{account}"

    def get(self, service: str, account: str) -> str | None:
        ctypes = self.ctypes
        wintypes = self.wintypes
        credential = ctypes.c_void_p()
        self.advapi32.CredReadW.restype = wintypes.BOOL
        if not self.advapi32.CredReadW(
            self._target(service, account),
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(credential),
        ):
            return None
        try:
            class Credential(ctypes.Structure):
                _fields_ = [
                    ("Flags", wintypes.DWORD),
                    ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)),
                    ("Persist", wintypes.DWORD),
                    ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR),
                ]

            data = ctypes.cast(credential, ctypes.POINTER(Credential)).contents
            return ctypes.string_at(data.CredentialBlob, data.CredentialBlobSize).decode("utf-8")
        finally:
            self.advapi32.CredFree(credential)

    def set(self, service: str, account: str, value: str) -> None:
        ctypes = self.ctypes
        wintypes = self.wintypes
        credential_blob = str(value).encode("utf-8")

        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        blob = (wintypes.BYTE * len(credential_blob)).from_buffer_copy(credential_blob)
        entry = Credential(
            Type=self.CRED_TYPE_GENERIC,
            TargetName=self._target(service, account),
            CredentialBlobSize=len(credential_blob),
            CredentialBlob=blob,
            Persist=self.CRED_PERSIST_LOCAL_MACHINE,
            UserName=account,
        )
        self.advapi32.CredWriteW.restype = wintypes.BOOL
        if not self.advapi32.CredWriteW(ctypes.byref(entry), 0, False):
            raise RuntimeError("credential_manager_write_failed")

    def delete(self, service: str, account: str) -> None:
        self.advapi32.CredDeleteW.restype = self.wintypes.BOOL
        if not self.advapi32.CredDeleteW(self._target(service, account), self.CRED_TYPE_GENERIC, 0):
            if self.ctypes.get_last_error() != 1168:  # ERROR_NOT_FOUND
                raise RuntimeError("credential_manager_delete_failed")


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
        if self.backend is None and not disabled:
            backend_class = {
                "Darwin": MacOSKeychainBackend,
                "Windows": WindowsCredentialManagerBackend,
            }.get(platform.system())
            if backend_class is not None:
                try:
                    self.backend = backend_class()
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
    "WindowsCredentialManagerBackend",
]
