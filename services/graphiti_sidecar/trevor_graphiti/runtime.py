from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from .config import SidecarConfig
from .gateway import GraphitiGateway
from .gemini_reranker import TrevorGeminiReranker
from .lexical_reranker import TrevorLexicalReranker
from .ollama_embedder import OllamaEmbedder


def embedded_runtime_supported(system_name: str, machine_name: str) -> bool:
    system = str(system_name or '').strip().lower()
    machine = str(machine_name or '').strip().lower()
    return not (system == 'darwin' and machine in {'x86_64', 'amd64', 'i386'})


def select_graphiti_llm_provider(
    requested_provider: str,
    gemini_api_key: str,
    nvidia_api_key: str,
) -> str:
    requested = str(requested_provider or 'auto').strip().lower()
    gemini_valid = str(gemini_api_key or '').strip().startswith('AIza')
    nvidia_configured = bool(str(nvidia_api_key or '').strip())
    if requested == 'gemini':
        if not gemini_valid:
            raise RuntimeError('gemini_credential_invalid')
        return 'gemini'
    if requested == 'nvidia':
        if not nvidia_configured:
            raise RuntimeError('nvidia_credential_missing')
        return 'nvidia'
    if gemini_valid:
        return 'gemini'
    if nvidia_configured:
        return 'nvidia'
    raise RuntimeError('graphiti_llm_credential_missing')


def _macos_keychain_secret(service: str, account: str) -> str:
    try:
        import Security
    except ImportError:
        return ''
    query = {
        Security.kSecClass: Security.kSecClassGenericPassword,
        Security.kSecAttrService: service,
        Security.kSecAttrAccount: account,
        Security.kSecReturnData: True,
        Security.kSecMatchLimit: Security.kSecMatchLimitOne,
    }
    authentication_ui = getattr(Security, 'kSecUseAuthenticationUI', None)
    authentication_ui_fail = getattr(Security, 'kSecUseAuthenticationUIFail', None)
    if authentication_ui is not None and authentication_ui_fail is not None:
        query[authentication_ui] = authentication_ui_fail
    try:
        status, data = Security.SecItemCopyMatching(query, None)
    except Exception:
        return ''
    if status != Security.errSecSuccess or data is None:
        return ''
    try:
        return bytes(data).decode('utf-8').strip()
    except (TypeError, UnicodeDecodeError):
        return ''


def load_runtime_secret(credential_name: str, env_name: str) -> str:
    credential_dir = str(os.getenv('CREDENTIALS_DIRECTORY', '') or '').strip()
    if credential_dir:
        path = Path(credential_dir) / credential_name
        try:
            value = path.read_text(encoding='utf-8').strip()
        except OSError:
            value = ''
        if value:
            return value
    environment_value = str(os.getenv(env_name, '') or '').strip()
    if environment_value:
        return environment_value
    keychain_disabled = str(
        os.getenv('TREVOR_DISABLE_KEYCHAIN', '') or ''
    ).strip().lower() in {'1', 'true', 'yes', 'on'}
    if keychain_disabled:
        return ''
    if platform.system() == 'Darwin':
        account = credential_name.replace('_', '-')
        service = str(
            os.getenv('TREVOR_PROVIDER_KEYCHAIN_SERVICE', 'trevor.providers')
            or 'trevor.providers'
        ).strip()
        value = _macos_keychain_secret(service, account)
        if value:
            return value
    return ''


async def await_driver_initialization(driver: object) -> None:
    initialization_task = getattr(driver, '_init_task', None)
    if initialization_task is not None:
        await initialization_task
        return
    await driver.build_indices_and_constraints()


@dataclass
class TrevorGraphitiRuntime:
    config: SidecarConfig
    graphiti: object
    gateway: GraphitiGateway
    embedder: OllamaEmbedder
    llm_provider: str
    rerank_provider: str

    @classmethod
    async def create(cls, config: SidecarConfig) -> 'TrevorGraphitiRuntime':
        os.environ.setdefault('GRAPHITI_TELEMETRY_ENABLED', 'false')
        if not embedded_runtime_supported(platform.system(), platform.machine()):
            raise RuntimeError('falkordblite_unsupported_architecture')
        gemini_api_key = load_runtime_secret('gemini_api_key', 'GEMINI_API_KEY')
        nvidia_api_key = load_runtime_secret('nvidia_api_key', 'NVIDIA_API_KEY')
        llm_provider = select_graphiti_llm_provider(
            config.llm_provider,
            gemini_api_key,
            nvidia_api_key,
        )

        from graphiti_core import Graphiti
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from graphiti_core.llm_client import LLMConfig
        from redislite.async_falkordb_client import AsyncFalkorDB

        graph_dir = config.data_dir / 'graphiti'
        graph_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(graph_dir, 0o700)
        embedded = AsyncFalkorDB(
            dbfilename=str(graph_dir / 'falkordb.db'),
            serverconfig={'bind': '127.0.0.1', 'port': '0'},
        )
        driver = FalkorDriver(falkor_db=embedded, database=config.graph_name)
        if llm_provider == 'gemini':
            from graphiti_core.llm_client.gemini_client import GeminiClient

            llm_config = LLMConfig(
                api_key=gemini_api_key,
                model=config.extraction_model,
                small_model=config.extraction_model,
                temperature=None,
                max_tokens=16384,
            )
            llm_client = GeminiClient(config=llm_config, max_tokens=16384)
            reranker = TrevorGeminiReranker(
                api_key=gemini_api_key, model=config.rerank_model
            )
            rerank_provider = 'gemini'
        else:
            from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

            llm_config = LLMConfig(
                api_key=nvidia_api_key,
                model=config.nvidia_extraction_model,
                small_model=config.nvidia_extraction_model,
                base_url=config.nvidia_base_url,
                temperature=0.1,
                max_tokens=16384,
            )
            llm_client = OpenAIGenericClient(
                config=llm_config,
                max_tokens=16384,
                structured_output_mode='json_object',
            )
            reranker = TrevorLexicalReranker()
            rerank_provider = 'lexical'
        embedder = OllamaEmbedder(
            base_url=config.ollama_base_url, model=config.embedding_model
        )
        graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=reranker,
            store_raw_episode_content=False,
            max_coroutines=1,
        )
        await await_driver_initialization(driver)
        gateway = GraphitiGateway(
            graphiti, query_concurrency=config.query_concurrency
        )
        return cls(
            config=config,
            graphiti=graphiti,
            gateway=gateway,
            embedder=embedder,
            llm_provider=llm_provider,
            rerank_provider=rerank_provider,
        )

    async def close(self) -> None:
        await self.graphiti.close()
        await self.embedder.close()


__all__ = [
    'TrevorGraphitiRuntime',
    'await_driver_initialization',
    'embedded_runtime_supported',
    'load_runtime_secret',
    'select_graphiti_llm_provider',
]
