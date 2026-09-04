import os
from unittest.mock import patch

from core.keychain_credentials import (
    KeychainCredentialStore,
    WindowsCredentialManagerBackend,
)
from tools.configure_ai_horde_credential import (
    ANONYMOUS_KEY,
    configure_anonymous,
    credential_status,
)


class _Backend:
    def __init__(self, value=None):
        self.value = value

    def get(self, _service, _account):
        return self.value

    def set(self, _service, _account, value):
        self.value = value

    def delete(self, _service, _account):
        self.value = None


def test_windows_backend_uses_stable_service_and_account_target():
    assert WindowsCredentialManagerBackend._target_name(
        "perob.ai-horde", "api-key"
    ) == "Trevor/perob.ai-horde/api-key"


def test_store_selects_windows_credential_manager_when_enabled():
    sentinel = _Backend()
    with patch.dict(os.environ, {}, clear=False), patch(
        "core.keychain_credentials.platform.system", return_value="Windows"
    ), patch(
        "core.keychain_credentials.WindowsCredentialManagerBackend",
        return_value=sentinel,
    ):
        os.environ.pop("TREVOR_DISABLE_KEYCHAIN", None)
        store = KeychainCredentialStore()

    assert store.backend is sentinel


def test_store_still_fails_closed_when_keychain_is_disabled_on_windows():
    with patch.dict(os.environ, {"TREVOR_DISABLE_KEYCHAIN": "true"}), patch(
        "core.keychain_credentials.platform.system", return_value="Windows"
    ):
        store = KeychainCredentialStore()

    assert store.backend is None


def test_ai_horde_status_never_exposes_the_secret():
    store = KeychainCredentialStore(backend=_Backend("private-value"))

    status = credential_status(store)

    assert status["configured"] is True
    assert "private-value" not in repr(status)


def test_anonymous_setup_uses_the_documented_public_key_without_returning_it():
    backend = _Backend()
    store = KeychainCredentialStore(backend=backend)

    result = configure_anonymous(store)

    assert backend.value == ANONYMOUS_KEY
    assert result["configured"] is True
    assert result["anonymous"] is True
    assert ANONYMOUS_KEY not in repr(result)
