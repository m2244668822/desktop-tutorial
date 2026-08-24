from __future__ import annotations

import asyncio
import re
from typing import Any

from .graphiti_contracts import CrossEncoderClient


class TrevorGeminiReranker(CrossEncoderClient):
    def __init__(self, *, api_key: str, model: str, client: Any | None = None):
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self.client = client
        self.model = model
        self._semaphore = asyncio.Semaphore(1)

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if len(passages) <= 1:
            return [(passage, 1.0) for passage in passages]
        from google.genai import types

        ranked = []
        async with self._semaphore:
            for passage in passages:
                prompt = (
                    'Score passage relevance to the query from 0 to 100. Return only the number.\n'
                    f'Query: {query}\nPassage: {passage}'
                )
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=[
                        types.Content(
                            role='user', parts=[types.Part.from_text(text=prompt)]
                        )
                    ],
                    config=types.GenerateContentConfig(
                        max_output_tokens=3,
                        system_instruction='Return one integer from 0 to 100.',
                    ),
                )
                match = re.search(r'\b(\d{1,3})\b', str(getattr(response, 'text', '') or ''))
                score = max(0.0, min(1.0, int(match.group(1)) / 100)) if match else 0.0
                ranked.append((passage, score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked


__all__ = ['TrevorGeminiReranker']
