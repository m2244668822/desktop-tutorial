from __future__ import annotations

import re

from .graphiti_contracts import CrossEncoderClient


TOKEN_RE = re.compile(r'[\w\u4e00-\u9fff]{2,}')


class TrevorLexicalReranker(CrossEncoderClient):
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        query_tokens = set(TOKEN_RE.findall(str(query or '').lower()))
        ranked: list[tuple[str, float]] = []
        for passage in passages:
            passage_tokens = set(TOKEN_RE.findall(str(passage or '').lower()))
            overlap = len(query_tokens & passage_tokens)
            denominator = max(1, len(query_tokens))
            ranked.append((passage, overlap / denominator))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked


__all__ = ['TrevorLexicalReranker']
