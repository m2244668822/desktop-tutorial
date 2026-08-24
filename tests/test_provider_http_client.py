import json
import unittest
from unittest.mock import patch


class _JsonResponse:
    def __init__(self, payload):
        self.payload = payload
        self.content = json.dumps(payload).encode('utf-8')
        self.status_code = 200


class _ErrorResponse(_JsonResponse):
    def __init__(self, status_code):
        super().__init__({'error': 'redacted'})
        self.status_code = status_code


class ProviderHttpClientTests(unittest.TestCase):
    def test_gemini_model_discovery_uses_native_models_endpoint(self):
        from core.provider_client import ProviderHttpClient
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={'GEMINI_API_KEY': 'gemini-test-value'},
            free_tier_confirmed={'gemini'},
        )
        client = ProviderHttpClient(registry)
        with patch(
            'core.provider_client.requests.get',
            return_value=_JsonResponse({'models': [{'name': 'models/gemini-3.7-flash'}]}),
        ) as get:
            models = client.list_models('gemini')

        self.assertEqual(
            'https://generativelanguage.googleapis.com/v1beta/models',
            get.call_args.args[0],
        )
        self.assertEqual({'gemini-3.7-flash'}, models)

    def test_model_discovery_preserves_authentication_failure_status(self):
        from core.provider_client import ProviderHttpClient
        from core.provider_registry import ProviderCallError, ProviderRegistry

        registry = ProviderRegistry(
            env={'GROQ_API_KEY': 'groq-test-value'},
            free_tier_confirmed={'groq'},
        )
        client = ProviderHttpClient(registry)
        with patch('core.provider_client.requests.get', return_value=_ErrorResponse(401)):
            with self.assertRaises(ProviderCallError) as raised:
                client.list_models('groq')

        self.assertEqual(401, raised.exception.status_code)

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

        self.assertEqual(1, endpoint.count('/accounts/'))
        self.assertIn('/client/v4/accounts/account-id/ai/run/', endpoint)
        self.assertTrue(endpoint.endswith('@cf/meta/llama-3.3-70b-instruct-fp8-fast'))


if __name__ == '__main__':
    unittest.main()
