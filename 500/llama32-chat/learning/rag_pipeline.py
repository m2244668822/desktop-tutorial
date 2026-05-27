"""
RAG Pipeline — 語意向量搜尋
優先 ChromaDB (持久化)，降級為純記憶體語意索引（均使用 embedding_engine）
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from embedding_engine import cosine, embed, embed_batch

logger = logging.getLogger("rag_pipeline")

# ── 共用工具 ────────────────────────────────────────────────


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_conversations(
    data: Any,
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []

    if isinstance(data, list):
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            prompt = item.get("prompt")
            response = item.get("response")
            if not prompt or not response:
                continue
            text = f"User: {prompt}\nAssistant: {response}"
            documents.append(text)
            metadatas.append(
                {
                    "timestamp": item.get("timestamp"),
                    "model": item.get("model"),
                    "status": item.get("status"),
                }
            )
            ids.append(str(item.get("id") or f"conv-{idx}"))

    return documents, metadatas, ids


def _format_context(retrieved: List[Dict[str, Any]]) -> str:
    if not retrieved:
        return ""
    lines = ["# Retrieved context"]
    for idx, item in enumerate(retrieved, start=1):
        meta = item.get("metadata", {})
        timestamp = meta.get("timestamp", "")
        model = meta.get("model", "")
        header = f"[{idx}]"
        if timestamp or model:
            header = f"[{idx}] ({timestamp} {model})".strip()
        lines.append(f"{header}\n{item.get('text', '')}")
    return "\n\n".join(lines)


# ── ChromaDB Pipeline ────────────────────────────────────────


class _OllamaEmbedFn:
    """ChromaDB embedding function wrapper for embedding_engine."""

    def __call__(self, input: List[str]) -> List[List[float]]:  # noqa: A002
        return embed_batch(input)


class RAGPipeline:
    def __init__(self, db_dir: Path, collection_name: str, embed_model: str = ""):
        self.db_dir = Path(db_dir)
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _get_collection(self, rebuild: bool = False):
        import chromadb

        if self._client is None:
            self.db_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.db_dir))

        if rebuild:
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:
                pass

        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=_OllamaEmbedFn(),
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def ensure_index(self, conversations_path: Path) -> int:
        col = self._get_collection()
        if col.count() > 0:
            return 0
        return self.index_conversations(conversations_path)

    def index_conversations(
        self, conversations_path: Path, rebuild: bool = False
    ) -> int:
        data = _load_json(conversations_path)
        docs, metas, ids = _parse_conversations(data)
        if not docs:
            return 0
        col = self._get_collection(rebuild=rebuild)
        col.add(documents=docs, metadatas=metas, ids=ids)
        return len(docs)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        col = self._get_collection()
        results = col.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        dists = (results.get("distances") or [[]])[0]
        return [
            {"text": d, "metadata": m or {}, "distance": dist}
            for d, m, dist in zip(docs, metas, dists)
        ]

    def format_context(self, retrieved: List[Dict[str, Any]]) -> str:
        return _format_context(retrieved)


# ── In-Memory Semantic RAG ───────────────────────────────────


class SimpleRAG:
    """純記憶體語意搜尋，使用 embedding_engine 的真實向量。"""

    def __init__(self):
        self._documents: List[str] = []
        self._metadatas: List[Dict[str, Any]] = []
        self._embeddings: List[List[float]] = []

    def ensure_index(self, conversations_path: Path) -> int:
        if self._documents:
            return 0
        return self.index_conversations(conversations_path)

    def index_conversations(
        self, conversations_path: Path, rebuild: bool = False
    ) -> int:
        data = _load_json(conversations_path)
        docs, metas, _ = _parse_conversations(data)
        if not docs:
            return 0
        if rebuild:
            self._documents = []
            self._metadatas = []
            self._embeddings = []
        self._documents = docs
        self._metadatas = metas
        logger.info("SimpleRAG: 向量化 %d 筆對話…", len(docs))
        self._embeddings = embed_batch(docs)
        logger.info("SimpleRAG: 向量化完成")
        return len(docs)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._documents:
            return []
        q_vec = embed(query)
        scored = [
            (i, cosine(q_vec, doc_vec)) for i, doc_vec in enumerate(self._embeddings)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            {
                "text": self._documents[i],
                "metadata": self._metadatas[i],
                "distance": 1.0 - score,
            }
            for i, score in scored[:top_k]
        ]

    def format_context(self, retrieved: List[Dict[str, Any]]) -> str:
        return _format_context(retrieved)


# ── Factory ──────────────────────────────────────────────────


def create_rag_pipeline(
    db_dir: Path,
    collection_name: str,
    embed_model: str = "",
    prefer_chroma: bool = True,
):
    if prefer_chroma:
        try:
            import chromadb  # noqa: F401

            return RAGPipeline(db_dir=db_dir, collection_name=collection_name)
        except Exception as e:
            logger.warning("ChromaDB 不可用，改用 SimpleRAG: %s", e)
    return SimpleRAG()
