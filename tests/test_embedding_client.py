import json
import os
import unittest
import urllib.error

from core.embedding_client import EmbeddingConfig, EmbeddingError, NemotronEmbeddingClient


class EmbeddingClientTests(unittest.TestCase):
    def test_query_and_passage_use_separate_contract_modes(self):
        calls = []

        def fake_request(url, payload, headers, timeout):
            body = json.loads(payload.decode("utf-8"))
            calls.append((url, body, headers, timeout))
            return json.dumps(
                {
                    "model": "nvidia/nemotron-3-embed-1b",
                    "data": [
                        {"index": 0, "embedding": [0.1, 0.2] * 1024},
                    ],
                }
            ).encode("utf-8")

        client = NemotronEmbeddingClient(
            EmbeddingConfig(base_url="https://example.test/v1"),
            api_key="nvapi-test",
            request_fn=fake_request,
        )
        self.assertEqual(2048, len(client.embed_one("query", input_type="query")))
        self.assertEqual(2048, len(client.embed_one("passage", input_type="passage")))
        self.assertEqual(["query", "passage"], [item[1]["input_type"] for item in calls])
        self.assertEqual("Bearer nvapi-test", calls[0][2]["Authorization"])

    def test_invalid_mode_and_missing_key_fail_closed(self):
        client = NemotronEmbeddingClient(api_key="")
        with self.assertRaisesRegex(EmbeddingError, "embedding_input_type_invalid"):
            client.embed_one("text", input_type="chat")
        with self.assertRaisesRegex(EmbeddingError, "nvidia_api_key_missing"):
            client.embed_one("text", input_type="query")

    def test_dimension_is_validated(self):
        def fake_request(url, payload, headers, timeout):
            return json.dumps({"data": [{"embedding": [0.1]}]}).encode("utf-8")

        client = NemotronEmbeddingClient(api_key="nvapi-test", request_fn=fake_request)
        with self.assertRaisesRegex(EmbeddingError, "embedding_dimension_mismatch"):
            client.embed_one("text", input_type="query")

    def test_http_401_and_429_keep_actionable_error_codes(self):
        def http_error(status):
            return urllib.error.HTTPError(
                url="https://example.test/v1/embeddings",
                code=status,
                msg="test",
                hdrs=None,
                fp=None,
            )

        for status, expected in (
            (401, "embedding_auth_failed"),
            (429, "embedding_rate_limited"),
        ):
            with self.subTest(status=status):
                client = NemotronEmbeddingClient(
                    api_key="nvapi-test",
                    request_fn=lambda *args, status=status, **kwargs: (_ for _ in ()).throw(
                        http_error(status)
                    ),
                )
                with self.assertRaisesRegex(EmbeddingError, expected):
                    client.embed_one("text", input_type="passage")


if __name__ == "__main__":
    unittest.main()
