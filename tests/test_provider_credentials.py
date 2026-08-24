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


class _FailIfReadBackend(_Backend):
    def __init__(self):
        super().__init__()
        self.called = False

    def get(self, service, account):
        self.called = True
        return None


class ProviderCredentialTests(unittest.TestCase):
    def test_staged_credentials_directory_disables_keychain_fallback(self):
        from core.keychain_credentials import KeychainCredentialStore
        from core.provider_credentials import ProviderCredentialResolver

        with tempfile.TemporaryDirectory() as tmp:
            backend = _FailIfReadBackend()
            resolver = ProviderCredentialResolver(
                credential_store=KeychainCredentialStore(backend=backend),
                credentials_directory=tmp,
            )
            result = resolver.resolve('groq')

        self.assertFalse(result.configured)
        self.assertEqual('none', result.source)
        self.assertFalse(backend.called)
    def test_systemd_credential_precedes_keychain_without_repr_leak(self):
        from core.keychain_credentials import KeychainCredentialStore
        from core.provider_credentials import ProviderCredentialResolver

        backend = _Backend({('trevor.providers', 'gemini-api-key'): 'keychain-secret'})
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'gemini_api_key').write_text('systemd-secret\n', encoding='utf-8')
            resolver = ProviderCredentialResolver(
                credential_store=KeychainCredentialStore(backend=backend),
                credentials_directory=tmp,
            )
            result = resolver.resolve('gemini')

        self.assertTrue(result.configured)
        self.assertEqual('systemd', result.source)
        self.assertEqual('systemd-secret', result.value)
        self.assertNotIn('systemd-secret', repr(result))

    def test_registry_prefers_resolver_over_legacy_environment(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={'NVIDIA_API_KEY': 'legacy-env-secret'},
            credential_resolver=lambda provider: 'keychain-secret' if provider == 'nvidia' else '',
        )

        self.assertEqual('keychain-secret', registry.credential_for('nvidia'))

    def test_missing_credential_has_public_status_only(self):
        from core.keychain_credentials import KeychainCredentialStore
        from core.provider_credentials import ProviderCredentialResolver

        result = ProviderCredentialResolver(
            credential_store=KeychainCredentialStore(backend=_Backend()),
            credentials_directory='/does/not/exist',
        ).resolve('groq')

        self.assertFalse(result.configured)
        self.assertEqual({'configured': False, 'source': 'none'}, result.public_status())


if __name__ == '__main__':
    unittest.main()
