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
                    ('trevor.providers', 'nvidia-api-key'): 'nvidia-secret',
                    ('trevor.providers', 'graphiti-token'): 'internal-secret',
                }
            )
        )

        self.assertEqual('gemini-secret', result['gemini_api_key'])
        self.assertEqual('nvidia-secret', result['nvidia_api_key'])
        self.assertEqual('internal-secret', result['graphiti_token'])

    def test_missing_required_credential_fails_closed(self):
        from tools.launch_graphiti_sidecar import load_graphiti_credentials

        with self.assertRaisesRegex(RuntimeError, 'graphiti_llm_credential_missing'):
            load_graphiti_credentials(_Store({}))

    def test_nvidia_only_llm_credential_is_accepted(self):
        from tools.launch_graphiti_sidecar import load_graphiti_credentials

        result = load_graphiti_credentials(
            _Store(
                {
                    ('trevor.providers', 'nvidia-api-key'): 'nvidia-secret',
                    ('trevor.providers', 'graphiti-token'): 'internal-secret',
                }
            )
        )

        self.assertEqual('', result['gemini_api_key'])
        self.assertEqual('nvidia-secret', result['nvidia_api_key'])

    def test_health_url_uses_the_configured_sidecar_address(self):
        from tools.launch_graphiti_sidecar import graphiti_health_url

        self.assertEqual(
            'http://127.0.0.1:9107/health',
            graphiti_health_url(
                {'TREVOR_GRAPHITI_HOST': '0.0.0.0', 'TREVOR_GRAPHITI_PORT': '9107'}
            ),
        )
        self.assertEqual(
            'http://graphiti.internal:8123/health',
            graphiti_health_url(
                {
                    'TREVOR_GRAPHITI_HOST': 'graphiti.internal',
                    'TREVOR_GRAPHITI_PORT': '8123',
                }
            ),
        )


if __name__ == '__main__':
    unittest.main()
