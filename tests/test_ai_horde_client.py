import unittest


class _CredentialStore:
    def __init__(self, value='horde-test-secret'):
        self.value = value

    def get_secret(self, service, account):
        from core.keychain_credentials import CredentialResult

        if not self.value:
            return CredentialResult(False, 'keychain', error_code='credential_missing')
        return CredentialResult(True, 'keychain', value=self.value)


class _Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request_json(self, method, url, *, headers, payload, timeout):
        self.calls.append(
            {
                'method': method,
                'url': url,
                'headers': dict(headers),
                'payload': payload,
                'timeout': timeout,
            }
        )
        return self.responses.pop(0)


class AIHordeClientTests(unittest.TestCase):
    def test_image_and_text_requests_use_keychain_secret(self):
        from core.ai_horde_client import AIHordeClient

        transport = _Transport([(202, {'id': 'image-id'}), (202, {'id': 'text-id'})])
        client = AIHordeClient(
            credential_store=_CredentialStore(),
            transport=transport,
            client_agent='Trevor:1.0:test',
        )

        image_id = client.submit('image', '雲海城市', {'width': 512, 'height': 512, 'steps': 24})
        text_id = client.submit('text', '整理重點', {'max_length': 128, 'temperature': 0.6})

        self.assertEqual('image-id', image_id)
        self.assertEqual('text-id', text_id)
        self.assertTrue(transport.calls[0]['url'].endswith('/v2/generate/async'))
        self.assertTrue(transport.calls[1]['url'].endswith('/v2/generate/text/async'))
        self.assertEqual('horde-test-secret', transport.calls[0]['headers']['apikey'])
        self.assertTrue(transport.calls[0]['payload']['censor_nsfw'])
        self.assertFalse(transport.calls[0]['payload']['nsfw'])
        self.assertNotIn('horde-test-secret', repr(client))

    def test_request_validation_rejects_unknown_and_unsafe_fields(self):
        from core.ai_horde_client import AIHordeError, validate_horde_request

        invalid_payloads = (
            {'kind': 'image', 'prompt': 'x', 'params': {'webhook': 'https://example.com'}},
            {'kind': 'image', 'prompt': 'x', 'params': {'width': 500}},
            {'kind': 'text', 'prompt': 'x', 'params': {'max_length': 2}},
            {'kind': 'audio', 'prompt': 'x', 'params': {}},
            {'kind': 'text', 'prompt': 'x', 'params': {}, 'secret': 'no'},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(AIHordeError) as raised:
                validate_horde_request(payload)
            self.assertEqual('invalid_request', raised.exception.code)

    def test_provider_errors_are_stable_and_do_not_leak_secret(self):
        from core.ai_horde_client import AIHordeClient, AIHordeError

        transport = _Transport([(429, {'message': 'secret provider details', 'rc': 'TooManyPrompts'})])
        client = AIHordeClient(credential_store=_CredentialStore(), transport=transport)

        with self.assertRaises(AIHordeError) as raised:
            client.submit('text', '測試', {})

        self.assertEqual('provider_rate_limited', raised.exception.code)
        self.assertTrue(raised.exception.retryable)
        self.assertNotIn('secret provider details', str(raised.exception))
        self.assertNotIn('horde-test-secret', repr(raised.exception))

    def test_missing_key_fails_closed_before_network(self):
        from core.ai_horde_client import AIHordeClient, AIHordeError

        transport = _Transport([])
        client = AIHordeClient(credential_store=_CredentialStore(''), transport=transport)

        with self.assertRaises(AIHordeError) as raised:
            client.submit('image', '測試', {})

        self.assertEqual('credential_missing', raised.exception.code)
        self.assertEqual([], transport.calls)


if __name__ == '__main__':
    unittest.main()
