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
        self.episode_payloads = []

    async def search(self, query, group_ids=None, num_results=10):
        self.active_queries += 1
        self.max_active_queries = max(self.max_active_queries, self.active_queries)
        await asyncio.sleep(0.01)
        self.active_queries -= 1
        return [{'fact': query, 'group_ids': group_ids, 'limit': num_results}]

    async def add_episode(self, **payload):
        self.episode_payloads.append(payload)
        self.active_writes += 1
        self.max_active_writes = max(self.max_active_writes, self.active_writes)
        await asyncio.sleep(0.01)
        self.active_writes -= 1
        return payload


class GraphitiSidecarContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_nvidia_client_disables_reasoning_for_structured_requests(self):
        from services.graphiti_sidecar.trevor_graphiti.nvidia_client import (
            NvidiaNoThinkingClient,
        )

        class Completions:
            def __init__(self):
                self.calls = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                return {'ok': True}

        completions = Completions()
        delegate = mock.Mock()
        delegate.chat.completions = completions
        client = NvidiaNoThinkingClient(delegate)

        result = await client.chat.completions.create(
            model='nvidia/nemotron-3-nano-30b-a3b',
            messages=[{'role': 'user', 'content': 'Return JSON'}],
            extra_body={'chat_template_kwargs': {'low_effort': True}},
        )

        self.assertEqual({'ok': True}, result)
        self.assertEqual(
            {
                'chat_template_kwargs': {
                    'low_effort': True,
                    'enable_thinking': False,
                }
            },
            completions.calls[0]['extra_body'],
        )

    def test_sidecar_adapters_implement_graphiti_client_contracts(self):
        from services.graphiti_sidecar.trevor_graphiti.gemini_reranker import (
            TrevorGeminiReranker,
        )
        from services.graphiti_sidecar.trevor_graphiti.graphiti_contracts import (
            CrossEncoderClient,
            EmbedderClient,
        )
        from services.graphiti_sidecar.trevor_graphiti.lexical_reranker import (
            TrevorLexicalReranker,
        )
        from services.graphiti_sidecar.trevor_graphiti.ollama_embedder import (
            OllamaEmbedder,
        )

        self.assertTrue(issubclass(OllamaEmbedder, EmbedderClient))
        self.assertTrue(issubclass(TrevorGeminiReranker, CrossEncoderClient))
        self.assertTrue(issubclass(TrevorLexicalReranker, CrossEncoderClient))

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

    def test_runtime_secret_prefers_environment_without_touching_keychain(self):
        from services.graphiti_sidecar.trevor_graphiti import runtime

        with mock.patch.dict(
            os.environ,
            {'NVIDIA_API_KEY': 'environment-secret'},
            clear=True,
        ), mock.patch.object(
            runtime, '_macos_keychain_secret', return_value='keychain-secret'
        ) as keychain:
            value = runtime.load_runtime_secret('nvidia_api_key', 'NVIDIA_API_KEY')

        self.assertEqual('environment-secret', value)
        keychain.assert_not_called()

    def test_runtime_secret_honors_noninteractive_keychain_disable(self):
        from services.graphiti_sidecar.trevor_graphiti import runtime

        with mock.patch.dict(
            os.environ,
            {'TREVOR_DISABLE_KEYCHAIN': 'true'},
            clear=True,
        ), mock.patch.object(
            runtime.platform, 'system', return_value='Darwin'
        ), mock.patch.object(
            runtime, '_macos_keychain_secret', return_value='keychain-secret'
        ) as keychain:
            value = runtime.load_runtime_secret('nvidia_api_key', 'NVIDIA_API_KEY')

        self.assertEqual('', value)
        keychain.assert_not_called()

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
        self.assertEqual('auto', config.llm_provider)
        self.assertEqual(
            'nvidia/nemotron-3-ultra-550b-a55b',
            config.nvidia_extraction_model,
        )
        self.assertEqual(4096, config.llm_max_tokens)
        self.assertEqual(90.0, config.llm_timeout_seconds)
        self.assertEqual('nomic-embed-text', config.embedding_model)
        with self.assertRaises(ValueError):
            SidecarConfig.from_env({'TREVOR_GRAPHITI_HOST': '0.0.0.0'})

        tuned = SidecarConfig.from_env(
            {
                'TREVOR_GRAPHITI_LLM_MAX_TOKENS': '2048',
                'TREVOR_GRAPHITI_LLM_TIMEOUT_SECONDS': '45',
            }
        )
        self.assertEqual(2048, tuned.llm_max_tokens)
        self.assertEqual(45.0, tuned.llm_timeout_seconds)

    def test_nvidia_graphiti_client_has_one_bounded_provider_attempt(self):
        root = Path(__file__).resolve().parents[1]
        runtime = (
            root / 'services' / 'graphiti_sidecar' / 'trevor_graphiti' / 'runtime.py'
        ).read_text(encoding='utf-8')

        self.assertIn('max_retries=0', runtime)
        self.assertIn('timeout=config.llm_timeout_seconds', runtime)
        self.assertIn('max_tokens=config.llm_max_tokens', runtime)
        self.assertIn("structured_output_mode='json_schema'", runtime)

    def test_embedded_runtime_rejects_unsupported_intel_macos_binary(self):
        from services.graphiti_sidecar.trevor_graphiti.runtime import (
            embedded_runtime_supported,
        )

        self.assertFalse(embedded_runtime_supported('Darwin', 'x86_64'))
        self.assertTrue(embedded_runtime_supported('Linux', 'x86_64'))
        self.assertTrue(embedded_runtime_supported('Darwin', 'arm64'))

    def test_graphiti_llm_provider_falls_back_to_nvidia_without_fake_gemini_key(self):
        from services.graphiti_sidecar.trevor_graphiti.runtime import (
            select_graphiti_llm_provider,
        )

        self.assertEqual(
            'gemini',
            select_graphiti_llm_provider('auto', 'AIza' + ('x' * 35), 'nvapi-key'),
        )
        self.assertEqual(
            'nvidia',
            select_graphiti_llm_provider('auto', 'nvapi-duplicated-value', 'nvapi-key'),
        )
        with self.assertRaisesRegex(RuntimeError, 'graphiti_llm_credential_missing'):
            select_graphiti_llm_provider('auto', '', '')

    async def test_lexical_reranker_is_deterministic_and_network_free(self):
        from services.graphiti_sidecar.trevor_graphiti.lexical_reranker import (
            TrevorLexicalReranker,
        )

        reranker = TrevorLexicalReranker()
        ranked = await reranker.rank(
            'trevor memory',
            ['unrelated text', 'trevor persistent memory', 'memory only'],
        )

        self.assertEqual('trevor persistent memory', ranked[0][0])
        self.assertGreater(ranked[0][1], ranked[-1][1])

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
        self.assertTrue(all('uuid' not in payload for payload in graph.episode_payloads))

    async def test_episode_name_makes_retries_idempotent(self):
        from services.graphiti_sidecar.trevor_graphiti.gateway import GraphitiGateway

        class Driver:
            async def execute_query(self, *_args, **_kwargs):
                return ([{'uuid': 'existing'}], None, None)

        graph = _FakeGraphiti()
        graph.driver = Driver()
        gateway = GraphitiGateway(graph, query_concurrency=1)

        result = await gateway.add_episode(
            name='trevor-content-hash',
            episode_body='body',
            source_description='test',
            reference_time='2026-08-21T00:00:00+00:00',
            episode_uuid='00000000-0000-5000-8000-000000000001',
        )

        self.assertTrue(result['duplicate'])
        self.assertEqual([], graph.episode_payloads)

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
