import unittest

from core.keychain_credentials import CredentialResult


class _Store:
    def __init__(self, values):
        self.values = values

    def get_secret(self, service, account):
        value = self.values.get((service, account), '')
        return CredentialResult(bool(value), 'keychain', value=value)


class GraphitiLauncherTests(unittest.TestCase):
    def test_loads_required_credentials_without_legacy_environment(self):
        from tools.launch_graphiti_sidecar import load_graphiti_credentials

        result = load_graphiti_credentials(
            _Store(
                {
                    ('trevor.providers', 'gemini-api-key'): 'gemini-secret',
                    ('trevor.providers', 'graphiti-token'): 'internal-secret',
                }
            )
        )

        self.assertEqual('gemini-secret', result['gemini_api_key'])
        self.assertEqual('internal-secret', result['graphiti_token'])

    def test_missing_required_credential_fails_closed(self):
        from tools.launch_graphiti_sidecar import load_graphiti_credentials

        with self.assertRaisesRegex(RuntimeError, 'gemini_credential_missing'):
            load_graphiti_credentials(_Store({}))


if __name__ == '__main__':
    unittest.main()
