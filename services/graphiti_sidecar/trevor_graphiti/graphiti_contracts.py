from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

try:
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    from graphiti_core.embedder.client import EmbedderClient
except ModuleNotFoundError as exc:
    if exc.name != 'graphiti_core':
        raise

    class EmbedderClient(ABC):
        @abstractmethod
        async def create(
            self,
            input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
        ) -> list[float]:
            raise NotImplementedError

        async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
            raise NotImplementedError

    class CrossEncoderClient(ABC):
        @abstractmethod
        async def rank(
            self, query: str, passages: list[str]
        ) -> list[tuple[str, float]]:
            raise NotImplementedError


__all__ = ['CrossEncoderClient', 'EmbedderClient']
