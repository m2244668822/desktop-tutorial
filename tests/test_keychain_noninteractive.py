import unittest
import os
from unittest.mock import patch


class _Security:
    kSecClass = 'class'
    kSecClassGenericPassword = 'generic'
    kSecAttrService = 'service'
    kSecAttrAccount = 'account'
    kSecReturnData = 'return_data'
    kSecMatchLimit = 'match_limit'
    kSecMatchLimitOne = 'one'
    kSecUseAuthenticationUI = 'authentication_ui'
    kSecUseAuthenticationUIFail = 'fail'
    errSecItemNotFound = -1
    errSecSuccess = 0

    def __init__(self):
        self.query = None

    def SecItemCopyMatching(self, query, _result):
        self.query = query
        return self.errSecItemNotFound, None


class KeychainNoninteractiveTests(unittest.TestCase):
    def test_keychain_backend_can_be_disabled_for_staged_credential_processes(self):
        from core.keychain_credentials import KeychainCredentialStore

        with patch.dict(os.environ, {'TREVOR_DISABLE_KEYCHAIN': 'true'}), patch(
            'core.keychain_credentials.platform.system', return_value='Darwin'
        ):
            store = KeychainCredentialStore()

        self.assertIsNone(store.backend)

    def test_keychain_reads_fail_closed_without_opening_authentication_ui(self):
        from core.keychain_credentials import MacOSKeychainBackend

        security = _Security()
        backend = MacOSKeychainBackend.__new__(MacOSKeychainBackend)
        backend.security = security

        self.assertIsNone(backend.get('trevor.providers', 'nvidia-api-key'))
        self.assertEqual(
            security.kSecUseAuthenticationUIFail,
            security.query[security.kSecUseAuthenticationUI],
        )
