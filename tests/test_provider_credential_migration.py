import tempfile
import unittest
from pathlib import Path


class _Backend:
    def __init__(self):
        self.values = {}

    def get(self, service, account):
        return self.values.get((service, account))

    def set(self, service, account, value):
        self.values[(service, account)] = value

    def delete(self, service, account):
        self.values.pop((service, account), None)


class ProviderCredentialMigrationTests(unittest.TestCase):
    def test_apply_moves_values_then_scrubs_plaintext_without_backup(self):
        from core.keychain_credentials import KeychainCredentialStore
        from tools.migrate_provider_credentials import migrate_env_file

        backend = _Backend()
        store = KeychainCredentialStore(backend=backend)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text(
                'NVAPI_API_KEY=nvidia-secret\n'
                'GEMINI_API_KEY=gemini-secret\n'
                'GROQ_API_KEY=groq-secret\n'
                'SAFE_SETTING=enabled\n',
                encoding='utf-8',
            )

            result = migrate_env_file(path, credential_store=store, apply=True)
            content = path.read_text(encoding='utf-8')

        self.assertTrue(result['ok'])
        self.assertEqual('nvidia-secret', backend.values[('trevor.providers', 'nvidia-api-key')])
        self.assertEqual('gemini-secret', backend.values[('trevor.providers', 'gemini-api-key')])
        self.assertEqual('groq-secret', backend.values[('trevor.providers', 'groq-api-key')])
        self.assertNotIn('nvidia-secret', content)
        self.assertNotIn('gemini-secret', content)
        self.assertNotIn('groq-secret', content)
        self.assertIn('SAFE_SETTING=enabled', content)
        self.assertFalse(list(path.parent.glob('*.bak*')))

    def test_placeholder_and_dry_run_do_not_write_or_scrub(self):
        from core.keychain_credentials import KeychainCredentialStore
        from tools.migrate_provider_credentials import migrate_env_file

        backend = _Backend()
        store = KeychainCredentialStore(backend=backend)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            original = 'NVIDIA_API_KEY=your_nvidia_api_key_here\n'
            path.write_text(original, encoding='utf-8')

            result = migrate_env_file(path, credential_store=store, apply=False)

            self.assertEqual(original, path.read_text(encoding='utf-8'))

        self.assertTrue(result['ok'])
        self.assertFalse(result['migrated'])
        self.assertFalse(backend.values)


if __name__ == '__main__':
    unittest.main()
