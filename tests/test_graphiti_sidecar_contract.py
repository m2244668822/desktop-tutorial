import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class _FakeGraphiti:
    def __init__(self):
        self.active_queries = 0
        self.max_active_queries = 0
        self.active_writes = 0
        self.max_active_writes = 0

    async def search(self, query, group_ids=None, num_results=10):
        self.active_queries += 1
        self.max_active_queries = max(self.max_active_queries, self.active_queries)
        await asyncio.sleep(0.01)
        self.active_queries -= 1
        return [{'fact': query, 'group_ids': group_ids, 'limit': num_results}]

    async def add_episode(self, **payload):
        self.active_writes += 1
        self.max_active_writes = max(self.max_active_writes, self.active_writes)
        await asyncio.sleep(0.01)
        self.active_writes -= 1
        return payload


class GraphitiSidecarContractTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_secret_prefers_systemd_then_native_keychain(self):
        from services.graphiti_sidecar.trevor_graphiti import runtime

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'gemini_api_key').write_text('systemd-secret\n', encoding='utf-8')
            with mock.patch.dict(
                os.environ,
                {'CREDENTIALS_DIRECTORY': tmp, 'GEMINI_API_KEY': 'env-secret'},
                clear=True,
            ), mock.patch.object(
                runtime, '_macos_keychain_secret', return_value='keychain-secret'
            ) as keychain:
                value = runtime.load_runtime_secret('gemini_api_key', 'GEMINI_API_KEY')

        self.assertEqual('systemd-secret', value)
        keychain.assert_not_called()

        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            runtime.platform, 'system', return_value='Darwin'
        ), mock.patch.object(
            runtime, '_macos_keychain_secret', return_value='keychain-secret'
        ):
            value = runtime.load_runtime_secret('gemini_api_key', 'GEMINI_API_KEY')

        self.assertEqual('keychain-secret', value)

    async def test_runtime_awaits_existing_driver_initialization_once(self):
        from services.graphiti_sidecar.trevor_graphiti.runtime import (
            await_driver_initialization,
        )

        class Driver:
            def __init__(self):
                self.build_calls = 0
                self._init_task = asyncio.create_task(self._initialize())

            async def _initialize(self):
                self.build_calls += 1

            async def build_indices_and_constraints(self):
                self.build_calls += 1

        driver = Driver()

        await await_driver_initialization(driver)

        self.assertEqual(1, driver.build_calls)

    async def test_runtime_builds_indices_when_driver_has_no_init_task(self):
        from services.graphiti_sidecar.trevor_graphiti.runtime import (
            await_driver_initialization,
        )

        class Driver:
            def __init__(self):
                self.build_calls = 0

            async def build_indices_and_constraints(self):
                self.build_calls += 1

        driver = Driver()

        await await_driver_initialization(driver)

        self.assertEqual(1, driver.build_calls)

    def test_config_is_private_and_pins_requested_models(self):
        from services.graphiti_sidecar.trevor_graphiti.config import SidecarConfig

        config = SidecarConfig.from_env({})

        self.assertEqual('127.0.0.1', config.host)
        self.assertEqual(8091, config.port)
        self.assertEqual('0.29.3', config.graphiti_version)
        self.assertEqual('0.10.0', config.falkordblite_version)
        self.assertEqual('gemini-3.7-flash', config.extraction_model)
        self.assertEqual('gemini-3.5-flash-lite', config.rerank_model)
        self.assertEqual('nomic-embed-text', config.embedding_model)
        with self.assertRaises(ValueError):
            SidecarConfig.from_env({'TREVOR_GRAPHITI_HOST': '0.0.0.0'})

    def test_embedded_runtime_rejects_unsupported_intel_macos_binary(self):
        from services.graphiti_sidecar.trevor_graphiti.runtime import (
            embedded_runtime_supported,
        )

        self.assertFalse(embedded_runtime_supported('Darwin', 'x86_64'))
        self.assertTrue(embedded_runtime_supported('Linux', 'x86_64'))
        self.assertTrue(embedded_runtime_supported('Darwin', 'arm64'))

    def test_sidecar_dependency_versions_are_isolated_and_pinned(self):
        root = Path(__file__).resolve().parents[1]
        pyproject = (root / 'services' / 'graphiti_sidecar' / 'pyproject.toml').read_text(
            encoding='utf-8'
        )

        self.assertIn('requires-python = ">=3.12,<3.13"', pyproject)
        self.assertIn('falkordblite==0.10.0', pyproject)
        self.assertIn('graphiti-core[falkordb,google-genai]', pyproject)
        self.assertIn('path = "../../vendor/graphiti"', pyproject)

    async def test_queries_are_bounded_and_writes_are_serialized(self):
        from services.graphiti_sidecar.trevor_graphiti.gateway import GraphitiGateway

        graph = _FakeGraphiti()
        gateway = GraphitiGateway(graph, query_concurrency=2)

        await asyncio.gather(*(gateway.search(f'q-{index}') for index in range(6)))
        await asyncio.gather(
            *(
                gateway.add_episode(
                    name=f'e-{index}',
                    episode_body='body',
                    source_description='test',
                    reference_time='2026-08-21T00:00:00+00:00',
                    episode_uuid=f'00000000-0000-5000-8000-{index:012d}',
                )
                for index in range(4)
            )
        )

        self.assertLessEqual(graph.max_active_queries, 2)
        self.assertEqual(1, graph.max_active_writes)

    async def test_gateway_public_results_are_structured(self):
        from services.graphiti_sidecar.trevor_graphiti.gateway import GraphitiGateway

        gateway = GraphitiGateway(_FakeGraphiti(), query_concurrency=1)
        result = await gateway.search('memory', group_ids=['trevor'], limit=3)

        self.assertEqual('memory', result[0]['fact'])
        self.assertEqual(['trevor'], result[0]['group_ids'])

    async def test_ollama_embedder_uses_batch_api_and_expected_model(self):
        from services.graphiti_sidecar.trevor_graphiti.ollama_embedder import OllamaEmbedder

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {'embeddings': [[0.1, 0.2], [0.3, 0.4]]}

        class Client:
            def __init__(self):
                self.calls = []

            async def post(self, url, json):
                self.calls.append((url, json))
                return Response()

        client = Client()
        embedder = OllamaEmbedder(
            base_url='http://127.0.0.1:11434', model='nomic-embed-text', client=client
        )

        result = await embedder.create_batch(['one', 'two'])

        self.assertEqual([[0.1, 0.2], [0.3, 0.4]], result)
        self.assertEqual('/api/embed', client.calls[0][0][-10:])
        self.assertEqual('nomic-embed-text', client.calls[0][1]['model'])


if __name__ == '__main__':
    unittest.main()
