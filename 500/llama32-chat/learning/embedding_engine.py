#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EmbeddingEngine — 統一向量化引擎
優先使用 ollama 本地 embedding（llama3.2 → 3072d）
無法連線時降級為 TF-IDF 稀疏向量（正規化後填充至 3072d）
"""

import hashlib
import logging
import math
import re
import time
from collections import Counter
from typing import Dict, List, Optional

import ollama

logger = logging.getLogger("embedding_engine")

EMBED_MODEL = "llama3.2"
EMBED_DIM = 3072
_cache: Dict[str, List[float]] = {}
_cache_max = 2000


def embed(text: str, retries: int = 2) -> List[float]:
    """回傳 text 的 3072d 向量。優先 ollama，降級 TF-IDF。"""
    text = (text or "").strip()[:4096]
    key = hashlib.md5(text.encode()).hexdigest()
    if key in _cache:
        return _cache[key]

    vec = _try_ollama(text, retries) or _tfidf_fallback(text)

    if len(_cache) >= _cache_max:
        # 移除最舊的 200 筆
        for k in list(_cache)[:200]:
            del _cache[k]
    _cache[key] = vec
    return vec


def embed_batch(texts: List[str]) -> List[List[float]]:
    return [embed(t) for t in texts]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── 內部方法 ────────────────────────────────────────────────


def _try_ollama(text: str, retries: int) -> Optional[List[float]]:
    for attempt in range(retries):
        try:
            resp = ollama.embeddings(model=EMBED_MODEL, prompt=text)
            vec = resp.get("embedding") or []
            if vec:
                return _pad_or_trim(vec, EMBED_DIM)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(0.5)
            else:
                logger.debug("ollama embed 失敗，改用 TF-IDF: %s", e)
    return None


def _tfidf_fallback(text: str) -> List[float]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    freq = Counter(tokens)
    total = sum(freq.values()) or 1
    vec = [0.0] * EMBED_DIM
    for tok, cnt in freq.items():
        idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % EMBED_DIM
        vec[idx] += cnt / total
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _pad_or_trim(vec: List[float], dim: int) -> List[float]:
    if len(vec) >= dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))
