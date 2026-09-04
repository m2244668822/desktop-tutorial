from __future__ import annotations

import os
import platform
import ctypes
from ctypes import POINTER, Structure, byref, c_ubyte, cast, sizeof
from ctypes import wintypes
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


class _WindowsCredential(Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", POINTER(c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialManagerBackend:
    """Store generic secrets in the current user's Windows Credential Manager."""

    _GENERIC = 1
    _PERSIST_LOCAL_MACHINE = 2
    _ERROR_NOT_FOUND = 1168
    _MAX_BLOB_BYTES = 2560
    _TARGET_PREFIX = "Trevor"

    @staticmethod
    def _last_error() -> int:
        return int(getattr(ctypes, "get_last_error", lambda: 0)())

    def __init__(self, *, library: Any | None = None):
        if library is None:
            from ctypes import WinDLL

            library = WinDLL("Advapi32.dll", use_last_error=True)
        self.library = library
        self.library.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            POINTER(POINTER(_WindowsCredential)),
        ]
        self.library.CredReadW.restype = wintypes.BOOL
        self.library.CredWriteW.argtypes = [POINTER(_WindowsCredential), wintypes.DWORD]
        self.library.CredWriteW.restype = wintypes.BOOL
        self.library.CredDeleteW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self.library.CredDeleteW.restype = wintypes.BOOL
        self.library.CredFree.argtypes = [wintypes.LPVOID]
        self.library.CredFree.restype = None

    @classmethod
    def _target_name(cls, service: str, account: str) -> str:
        service_name = str(service or "").strip()
        account_name = str(account or "").strip()
        if not service_name or not account_name:
            raise RuntimeError("credential_identity_invalid")
        target = f"{cls._TARGET_PREFIX}/{service_name}/{account_name}"
        if len(target) > 32000 or "\x00" in target:
            raise RuntimeError("credential_identity_invalid")
        return target

    def get(self, service: str, account: str) -> str | None:
        target = self._target_name(service, account)
        pointer = POINTER(_WindowsCredential)()
        if not self.library.CredReadW(target, self._GENERIC, 0, byref(pointer)):
            if self._last_error() == self._ERROR_NOT_FOUND:
                return None
            raise RuntimeError("credential_read_failed")
        try:
            credential = pointer.contents
            size = int(credential.CredentialBlobSize)
            if size == 0:
                return None
            if size < 0 or size > self._MAX_BLOB_BYTES or not credential.CredentialBlob:
                raise RuntimeError("credential_blob_invalid")
            raw = bytes(credential.CredentialBlob[index] for index in range(size))
            try:
                return raw.decode("utf-16-le")
            except UnicodeDecodeError as exc:
                raise RuntimeError("credential_blob_invalid") from exc
        finally:
            self.library.CredFree(cast(pointer, wintypes.LPVOID))

    def set(self, service: str, account: str, value: str) -> None:
        from ctypes import create_string_buffer, memset

        target = self._target_name(service, account)
        secret = str(value or "")
        encoded = secret.encode("utf-16-le")
        if not encoded or len(encoded) > self._MAX_BLOB_BYTES:
            raise RuntimeError("credential_blob_invalid")
        buffer = create_string_buffer(encoded, len(encoded))
        credential = _WindowsCredential()
        credential.Type = self._GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = cast(buffer, POINTER(c_ubyte))
        credential.Persist = self._PERSIST_LOCAL_MACHINE
        credential.UserName = str(account)
        try:
            if not self.library.CredWriteW(byref(credential), 0):
                raise RuntimeError("credential_write_failed")
        finally:
            memset(buffer, 0, sizeof(buffer))

    def delete(self, service: str, account: str) -> None:
        target = self._target_name(service, account)
        if self.library.CredDeleteW(target, self._GENERIC, 0):
            return
        if self._last_error() != self._ERROR_NOT_FOUND:
            raise RuntimeError("credential_delete_failed")


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
        if self.backend is None and not disabled and platform.system() == "Windows":
            try:
                self.backend = WindowsCredentialManagerBackend()
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
