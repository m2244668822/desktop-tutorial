"""NVIDIA Nemotron-3-Embed-1B client for retrieval only.

This client is intentionally separate from ModelRouter. Embeddings support
indexing and retrieval; they do not provide chat, planning, or tool calling.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib import request as urllib_request


class EmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str = "nvidia/nemotron-3-embed-1b"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    dimension: int = 2048
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        return cls(
            model=os.getenv("EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b"),
            base_url=os.getenv(
                "EMBEDDING_BASE_URL",
                os.getenv("NVIDIA_EMBED_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            ).rstrip("/"),
            dimension=int(os.getenv("EMBEDDING_DIMENSION", "2048")),
            timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")),
        )


class NemotronEmbeddingClient:
    def __init__(
        self,
        config: EmbeddingConfig | None = None,
        *,
        api_key: str | None = None,
        request_fn: Callable[..., bytes] | None = None,
    ):
        self.config = config or EmbeddingConfig.from_env()
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY", "")
        self._request_fn = request_fn or self._request

    @staticmethod
    def _request(url: str, payload: bytes, headers: dict[str, str], timeout: float) -> bytes:
        req = urllib_request.Request(url, data=payload, headers=headers, method="POST")
        with urllib_request.urlopen(req, timeout=timeout) as response:
            return response.read()

    def embed(self, texts: Iterable[str], *, input_type: str) -> list[list[float]]:
        if input_type not in {"query", "passage"}:
            raise EmbeddingError("embedding_input_type_invalid")
        values = [str(item) for item in texts]
        if not values:
            raise EmbeddingError("embedding_input_empty")
        if not self.api_key:
            raise EmbeddingError("nvidia_api_key_missing")
        if not self.config.model.startswith("nvidia/nemotron-3-embed-"):
            raise EmbeddingError("embedding_model_not_nemotron")

        body = json.dumps(
            {
                "input": values,
                "model": self.config.model,
                "input_type": input_type,
                "encoding_format": "float",
            }
        ).encode("utf-8")
        try:
            raw = self._request_fn(
                f"{self.config.base_url}/embeddings",
                body,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                self.config.timeout_seconds,
            )
            response = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise EmbeddingError("embedding_auth_failed") from exc
            if exc.code == 429:
                raise EmbeddingError("embedding_rate_limited") from exc
            raise EmbeddingError(f"embedding_http_{exc.code}") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise EmbeddingError("embedding_timeout") from exc
        except urllib.error.URLError as exc:
            raise EmbeddingError("embedding_request_failed") from exc
        except Exception as exc:
            raise EmbeddingError("embedding_request_failed") from exc

        rows = response.get("data") if isinstance(response, dict) else None
        if not isinstance(rows, list) or len(rows) != len(values):
            raise EmbeddingError("embedding_count_mismatch")
        vectors: list[list[float]] = []
        for row in rows:
            vector = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(vector, list) or len(vector) != self.config.dimension:
                raise EmbeddingError("embedding_dimension_mismatch")
            vectors.append([float(item) for item in vector])
        return vectors

    def embed_one(self, text: str, *, input_type: str) -> list[float]:
        return self.embed([text], input_type=input_type)[0]
