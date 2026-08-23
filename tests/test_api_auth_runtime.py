import tempfile
import unittest
from pathlib import Path


class _Backend:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, service, account):
        return self.values.get((service, account))

    def set(self, service, account, value):
        self.values[(service, account)] = value

    def delete(self, service, account):
        self.values.pop((service, account), None)


class APIAuthRuntimeTests(unittest.TestCase):
    def test_systemd_hmac_secret_precedes_keychain(self):
        from core.api_auth import build_api_key_store
        from core.keychain_credentials import KeychainCredentialStore

        backend = _Backend({('trevor.auth', 'api-key-hmac'): 'k' * 32})
        with tempfile.TemporaryDirectory() as tmp:
            credentials = Path(tmp) / 'credentials'
            credentials.mkdir()
            (credentials / 'trevor_api_hmac').write_text('s' * 32, encoding='utf-8')
            store, status = build_api_key_store(
                Path(tmp) / 'data',
                credentials_directory=credentials,
                credential_store=KeychainCredentialStore(backend=backend),
            )

        self.assertIsNotNone(store)
        self.assertEqual('systemd', status['source'])
        self.assertNotIn('s' * 32, repr(status))

    def test_missing_hmac_secret_disables_auth_store(self):
        from core.api_auth import build_api_key_store
        from core.keychain_credentials import KeychainCredentialStore

        with tempfile.TemporaryDirectory() as tmp:
            store, status = build_api_key_store(
                Path(tmp),
                credential_store=KeychainCredentialStore(backend=_Backend()),
            )

        self.assertIsNone(store)
        self.assertEqual({'configured': False, 'source': 'none'}, status)


if __name__ == '__main__':
    unittest.main()
