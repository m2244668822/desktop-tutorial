import json
import unittest


class ProviderHttpClientTests(unittest.TestCase):
    def test_wire_payload_removes_internal_context_and_serializes_content(self):
        from core.provider_client import ProviderHttpClient

        request = {
            'request_type': 'candidate',
            'model': 'model-id',
            'trevor_context': {'message': 'private-safe-copy'},
            'messages': [{'role': 'user', 'content': {'message': 'safe'}}],
            'stream': False,
        }
        wire = ProviderHttpClient.wire_payload(request)

        self.assertNotIn('trevor_context', wire)
        self.assertNotIn('request_type', wire)
        self.assertEqual({'message': 'safe'}, json.loads(wire['messages'][0]['content']))

    def test_cloudflare_endpoint_uses_account_and_model(self):
        from core.provider_client import ProviderHttpClient
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={
                'CLOUDFLARE_API_TOKEN': 'cf-test-token',
                'CLOUDFLARE_ACCOUNT_ID': 'account-id',
                'CLOUDFLARE_PLAN': 'free',
            },
            free_tier_confirmed={'cloudflare'},
        )
        client = ProviderHttpClient(registry)
        endpoint = client.endpoint_for('cloudflare')

        self.assertIn('/accounts/account-id/ai/run/', endpoint)
        self.assertTrue(endpoint.endswith('@cf/meta/llama-3.3-70b-instruct-fp8-fast'))


if __name__ == '__main__':
    unittest.main()
