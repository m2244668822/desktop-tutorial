from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class SidecarConfig:
    host: str
    port: int
    data_dir: Path
    graph_name: str
    graphiti_version: str
    falkordblite_version: str
    llm_provider: str
    extraction_model: str
    rerank_model: str
    nvidia_extraction_model: str
    nvidia_base_url: str
    llm_max_tokens: int
    llm_timeout_seconds: float
    embedding_model: str
    ollama_base_url: str
    query_concurrency: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> 'SidecarConfig':
        values = os.environ if env is None else env
        host = str(values.get('TREVOR_GRAPHITI_HOST', '127.0.0.1') or '127.0.0.1').strip()
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError('TREVOR_GRAPHITI_HOST must be a loopback IP') from exc
        if not address.is_loopback:
            raise ValueError('Graphiti sidecar must bind to loopback only')
        deployment = str(values.get('TREVOR_DEPLOYMENT', '') or '').strip().lower()
        if values.get('TREVOR_DATA_DIR'):
            data_dir = Path(str(values['TREVOR_DATA_DIR'])).expanduser()
        elif deployment == 'oci':
            data_dir = Path('/var/lib/trevor')
        elif os.name == 'nt':
            data_dir = Path.home() / 'AppData' / 'Local' / 'Trevor'
        else:
            data_dir = Path.home() / 'Library' / 'Application Support' / 'Trevor'
        query_concurrency = max(
            1, min(2, int(values.get('TREVOR_GRAPHITI_QUERY_CONCURRENCY', '1') or '1'))
        )
        llm_provider = str(
            values.get('TREVOR_GRAPHITI_LLM_PROVIDER', 'auto') or 'auto'
        ).strip().lower()
        if llm_provider not in {'auto', 'gemini', 'nvidia'}:
            raise ValueError('TREVOR_GRAPHITI_LLM_PROVIDER must be auto, gemini, or nvidia')
        return cls(
            host=host,
            port=int(values.get('TREVOR_GRAPHITI_PORT', '8091') or '8091'),
            data_dir=data_dir.expanduser().resolve(),
            graph_name=str(values.get('TREVOR_GRAPHITI_GRAPH', 'trevor') or 'trevor'),
            graphiti_version='0.29.3',
            falkordblite_version='0.10.0',
            llm_provider=llm_provider,
            extraction_model=str(
                values.get('TREVOR_GRAPHITI_EXTRACTION_MODEL', 'gemini-3.7-flash')
                or 'gemini-3.7-flash'
            ),
            rerank_model=str(
                values.get('TREVOR_GRAPHITI_RERANK_MODEL', 'gemini-3.5-flash-lite')
                or 'gemini-3.5-flash-lite'
            ),
            nvidia_extraction_model=str(
                values.get(
                    'TREVOR_GRAPHITI_NVIDIA_MODEL',
                    'nvidia/nemotron-3-ultra-550b-a55b',
                )
                or 'nvidia/nemotron-3-ultra-550b-a55b'
            ),
            nvidia_base_url=str(
                values.get(
                    'TREVOR_GRAPHITI_NVIDIA_BASE_URL',
                    'https://integrate.api.nvidia.com/v1',
                )
                or 'https://integrate.api.nvidia.com/v1'
            ).rstrip('/'),
            llm_max_tokens=max(
                512,
                min(
                    16384,
                    int(values.get('TREVOR_GRAPHITI_LLM_MAX_TOKENS', '4096') or '4096'),
                ),
            ),
            llm_timeout_seconds=max(
                10.0,
                min(
                    300.0,
                    float(
                        values.get('TREVOR_GRAPHITI_LLM_TIMEOUT_SECONDS', '90') or '90'
                    ),
                ),
            ),
            embedding_model=str(
                values.get('TREVOR_GRAPHITI_EMBEDDING_MODEL', 'nomic-embed-text')
                or 'nomic-embed-text'
            ),
            ollama_base_url=str(
                values.get('TREVOR_OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
                or 'http://127.0.0.1:11434'
            ).rstrip('/'),
            query_concurrency=query_concurrency,
        )
