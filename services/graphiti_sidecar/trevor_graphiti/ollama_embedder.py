from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .graphiti_contracts import EmbedderClient


class OllamaEmbedder(EmbedderClient):
    def __init__(
        self,
        *,
        base_url: str,
        model: str = 'nomic-embed-text',
        client: Any | None = None,
    ):
        if client is None:
            import httpx

            client = httpx.AsyncClient(timeout=30)
        self.base_url = str(base_url or '').rstrip('/')
        self.model = str(model or 'nomic-embed-text')
        self.client = client

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        if isinstance(input_data, str):
            text = input_data
        else:
            text = ' '.join(str(item) for item in input_data)
        embeddings = await self.create_batch([text])
        return embeddings[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        response = await self.client.post(
            f'{self.base_url}/api/embed',
            json={'model': self.model, 'input': [str(item) for item in input_data_list]},
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get('embeddings', []) if isinstance(payload, dict) else []
        if len(embeddings) != len(input_data_list):
            raise RuntimeError('ollama_embedding_count_mismatch')
        return [[float(value) for value in embedding] for embedding in embeddings]

    async def close(self) -> None:
        close = getattr(self.client, 'aclose', None)
        if callable(close):
            await close()


__all__ = ['OllamaEmbedder']
