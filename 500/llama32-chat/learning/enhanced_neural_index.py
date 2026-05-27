#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增強型 RAG 神經索引系統 (Enhanced RAG Neural Index System)
擴展 RAG 索引的神經元能力，支持：
1. 多維向量嵌入（高維度向量空間）
2. 動態神經元叢集（Neuron Clustering）
3. 記憶增強檢索（Memory-Augmented Retrieval）
4. 自適應重排名（Adaptive Re-ranking）
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from embedding_engine import embed, cosine, EMBED_DIM


class EnhancedNeuralIndex:
    """增強型神經索引 - 擴展 RAG 能力"""

    def __init__(
        self, index_dir: str = "data/neural_index", dimensions: int = EMBED_DIM
    ):
        """
        初始化神經索引

        Args:
            index_dir: 索引存儲目錄
            dimensions: 向量維度（支援 768/1536/2048/4096，推薦 2048+ 以獲得最佳性能）
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.dimensions = dimensions
        self.base_connection_limit = 8
        self.max_connection_limit = 24
        self.neuron_index_file = self.index_dir / "neuron_index.json"
        self.neural_graph_file = self.index_dir / "neural_graph.json"
        self.memory_cache_file = self.index_dir / "memory_cache.json"
        self.retrieval_stats_file = self.index_dir / "retrieval_stats.json"

        # 核心數據結構
        self.neurons: Dict[str, Dict] = self._load_neurons()
        self.neural_graph: Dict[str, List[Tuple[str, float]]] = self._load_graph()
        self.memory_cache: Dict[str, Any] = self._load_cache()
        self.retrieval_stats = self._load_stats()

        # 神經元計數器
        self.neuron_counter = (
            max([int(n.split("_")[1]) for n in self.neurons.keys()], default=0) + 1
        )

        print(f"✅ 神經索引已初始化: {len(self.neurons)} 個神經元, 維度: {dimensions}")

    def add_document(
        self,
        doc_id: str,
        content: str,
        metadata: Dict[str, Any] = None,
        embedding: Optional[List[float]] = None,
    ) -> str:
        """
        添加文檔到神經索引

        Args:
            doc_id: 文檔 ID
            content: 文檔內容
            metadata: 元數據
            embedding: 嵌入向量（如果為 None，會生成隨機向量用於演示）

        Returns:
            分配的神經元 ID
        """
        if embedding is None:
            embedding = embed(content)

        # 創建神經元
        neuron_id = f"neuron_{self.neuron_counter}"
        self.neuron_counter += 1

        neuron = {
            "id": neuron_id,
            "doc_id": doc_id,
            "content": content,
            "embedding": embedding,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "activation_count": 0,
            "importance_score": 0.5,
            "connected_neurons": [],
            "learned_patterns": [],
            "quality_metrics": {"relevance": 0.5, "clarity": 0.5, "completeness": 0.5},
        }

        self.neurons[neuron_id] = neuron

        # 建立神經連接
        self._establish_neural_connections(neuron_id)

        return neuron_id

    def retrieve(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        use_neural_reranking: bool = True,
        expand_bridges: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        從神經索引中檢索

        Args:
            query_embedding: 查詢向量
            top_k: 返回最多 k 個結果
            use_neural_reranking: 是否使用神經元重排名

        Returns:
            檢索結果列表
        """
        if not self.neurons:
            return []

        # 計算相似度
        similarities = []
        for neuron_id, neuron in self.neurons.items():
            similarity = self._cosine_similarity(query_embedding, neuron["embedding"])
            similarities.append((neuron_id, similarity, neuron))

        # 排序
        similarities.sort(key=lambda x: x[1], reverse=True)

        # 取 top_k
        results = similarities[:top_k]

        # 神經元重排名
        if use_neural_reranking:
            results = self._apply_neural_reranking(results, query_embedding)

        # 橋接擴展：透過高權重連接補足對接能力
        if expand_bridges:
            results = self._expand_via_neural_bridges(
                results, query_embedding, top_k=top_k
            )

        # 更新檢索統計
        self._update_retrieval_stats(results)

        # 激活神經元
        for neuron_id, _, _ in results:
            self.neurons[neuron_id]["activation_count"] += 1

        # 格式化結果
        formatted_results = []
        for neuron_id, similarity, neuron in results:
            formatted_results.append(
                {
                    "neuron_id": neuron_id,
                    "doc_id": neuron["doc_id"],
                    "content": neuron["content"],
                    "similarity": float(similarity),
                    "metadata": neuron["metadata"],
                    "activation_history": neuron["activation_count"],
                    "importance": neuron["importance_score"],
                }
            )

        return formatted_results

    def _dynamic_connection_limit(self) -> int:
        """根據神經元規模動態調整連接上限"""
        if not self.neurons:
            return self.base_connection_limit
        growth = int(math.log2(len(self.neurons) + 1))
        return min(self.max_connection_limit, self.base_connection_limit + growth)

    def _establish_neural_connections(
        self, neuron_id: str, connection_limit: Optional[int] = None
    ):
        """建立神經元之間的連接"""
        if connection_limit is None:
            connection_limit = self._dynamic_connection_limit()

        if neuron_id not in self.neural_graph:
            self.neural_graph[neuron_id] = []

        target_neuron = self.neurons[neuron_id]
        target_embedding = target_neuron["embedding"]

        # 找到最相似的神經元
        connections = []
        for other_id, other_neuron in self.neurons.items():
            if other_id != neuron_id:
                similarity = self._cosine_similarity(
                    target_embedding, other_neuron["embedding"]
                )
                connections.append((other_id, similarity))

        # 排序並保留前 connection_limit 個
        connections.sort(key=lambda x: x[1], reverse=True)
        self.neural_graph[neuron_id] = connections[:connection_limit]

        # 建立雙向連接
        for connected_id, weight in self.neural_graph[neuron_id]:
            if connected_id not in self.neural_graph:
                self.neural_graph[connected_id] = []

            # 檢查是否已存在反向連接
            if not any(n[0] == neuron_id for n in self.neural_graph[connected_id]):
                self.neural_graph[connected_id].append((neuron_id, weight))
                self.neural_graph[connected_id].sort(key=lambda x: x[1], reverse=True)
                self.neural_graph[connected_id] = self.neural_graph[connected_id][
                    :connection_limit
                ]

    def _expand_via_neural_bridges(
        self, results: List[Tuple], query_embedding: List[float], top_k: int
    ) -> List[Tuple]:
        """沿著神經連接進行一跳橋接擴展，提高對接檢索率"""
        if not results:
            return results

        merged: Dict[str, Tuple[str, float, Dict[str, Any]]] = {
            neuron_id: (neuron_id, score, neuron)
            for neuron_id, score, neuron in results
        }

        for neuron_id, base_score, _ in results:
            neighbors = self.neural_graph.get(neuron_id, [])
            for neighbor_id, edge_weight in neighbors[:5]:
                neighbor = self.neurons.get(neighbor_id)
                if not neighbor:
                    continue

                semantic_score = self._cosine_similarity(
                    query_embedding, neighbor["embedding"]
                )
                bridge_score = (
                    (base_score * 0.55) + (semantic_score * 0.35) + (edge_weight * 0.10)
                )

                existing = merged.get(neighbor_id)
                if (existing is None) or (bridge_score > existing[1]):
                    merged[neighbor_id] = (neighbor_id, bridge_score, neighbor)

        reranked = sorted(merged.values(), key=lambda x: x[1], reverse=True)
        return reranked[:top_k]

    def _apply_neural_reranking(
        self, results: List[Tuple], query_embedding: List[float]
    ) -> List[Tuple]:
        """應用神經元重排名"""
        reranked = []

        for neuron_id, similarity, neuron in results:
            # 計算綜合分數
            score = similarity  # 基礎相似度

            # 激活歷史加權
            activation_weight = logit(neuron["activation_count"] / 100)
            score += activation_weight * 0.1

            # 重要性加權
            score += neuron["importance_score"] * 0.1

            # 質量度量加權
            quality = sum(neuron["quality_metrics"].values()) / 3
            score += quality * 0.1

            # 神經連接加權
            if neuron_id in self.neural_graph:
                connectivity = len(self.neural_graph[neuron_id]) / 5  # 正常化
                score += connectivity * 0.05

            reranked.append((neuron_id, score, neuron))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    def update_neuron_importance(self, neuron_id: str, new_score: float):
        """更新神經元的重要性分數"""
        if neuron_id in self.neurons:
            self.neurons[neuron_id]["importance_score"] = max(0, min(1, new_score))

    def learn_from_patterns(self, neuron_id: str, patterns: List[str]):
        """教導神經元學習模式"""
        if neuron_id in self.neurons:
            self.neurons[neuron_id]["learned_patterns"].extend(patterns)
            self.neurons[neuron_id]["learned_patterns"] = list(
                set(self.neurons[neuron_id]["learned_patterns"])
            )

    def get_neuron_cluster(self, neuron_id: str, depth: int = 2) -> Dict[str, Any]:
        """獲取神經元及其連接的叢集"""
        if neuron_id not in self.neurons:
            return {}

        cluster = {
            "root_neuron": self.neurons[neuron_id],
            "connected_neurons": [],
            "distances": {},
        }

        # 獲取直接連接
        if neuron_id in self.neural_graph:
            for connected_id, weight in self.neural_graph[neuron_id]:
                cluster["connected_neurons"].append(self.neurons[connected_id])
                cluster["distances"][connected_id] = weight

        return cluster

    def optimize_index(self):
        """優化索引性能"""
        print("📊 優化神經索引...")

        dynamic_limit = self._dynamic_connection_limit()

        # 移除低活躍度的神經元
        low_activity_neurons = [
            nid
            for nid, neuron in self.neurons.items()
            if neuron["activation_count"] < 1
        ]

        print(f"   低活躍度神經元: {len(low_activity_neurons)}")

        # 更新神經連接
        for neuron_id in self.neurons.keys():
            self._establish_neural_connections(
                neuron_id, connection_limit=dynamic_limit
            )

        # 計算統計信息
        stats = {
            "total_neurons": len(self.neurons),
            "total_connections": sum(
                len(conns) for conns in self.neural_graph.values()
            ),
            "average_activation": (
                sum(n["activation_count"] for n in self.neurons.values())
                / len(self.neurons)
            )
            if self.neurons
            else 0,
            "dynamic_connection_limit": dynamic_limit,
            "optimization_timestamp": datetime.now().isoformat(),
        }

        print(
            f"   優化完成: {stats['total_neurons']} 神經元, "
            f"{stats['total_connections']} 連接"
        )

        return stats

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        return cosine(vec1, vec2)

    def embed_query(self, text: str) -> List[float]:
        """外部查詢使用相同 embedding。"""
        return embed(text)

    def _update_retrieval_stats(self, results: List[Tuple]):
        """更新檢索統計"""
        if "retrievals" not in self.retrieval_stats:
            self.retrieval_stats["retrievals"] = []

        self.retrieval_stats["retrievals"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "results_count": len(results),
                "neuron_ids": [r[0] for r in results],
            }
        )

    def _load_neurons(self) -> Dict[str, Dict]:
        """加載神經元"""
        try:
            with open(self.neuron_index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_graph(self) -> Dict[str, List[Tuple[str, float]]]:
        """加載神經圖"""
        try:
            with open(self.neural_graph_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: [(n, w) for n, w in v] for k, v in data.items()}
        except Exception:
            return {}

    def _load_cache(self) -> Dict:
        """加載記憶快取"""
        try:
            with open(self.memory_cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_stats(self) -> Dict:
        """加載統計信息"""
        try:
            with open(self.retrieval_stats_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_index(self):
        """保存索引"""
        try:
            with open(self.neuron_index_file, "w", encoding="utf-8") as f:
                json.dump(self.neurons, f, ensure_ascii=False, indent=2)

            # 保存神經圖（轉換為序列化格式）
            graph_data = {k: v for k, v in self.neural_graph.items()}
            with open(self.neural_graph_file, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)

            with open(self.memory_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.memory_cache, f, ensure_ascii=False, indent=2)

            with open(self.retrieval_stats_file, "w", encoding="utf-8") as f:
                json.dump(self.retrieval_stats, f, ensure_ascii=False, indent=2)

            print("✅ 索引已保存")
        except Exception as e:
            print(f"❌ 保存索引失敗: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """獲取索引統計"""
        total_neurons = len(self.neurons)
        total_connections = sum(len(c) for c in self.neural_graph.values())
        return {
            "total_neurons": total_neurons,
            "total_connections": total_connections,
            "avg_connection_degree": (total_connections / total_neurons)
            if total_neurons
            else 0.0,
            "dynamic_connection_limit": self._dynamic_connection_limit(),
            "vector_dimensions": self.dimensions,
            "average_activation": (
                sum(n["activation_count"] for n in self.neurons.values())
                / len(self.neurons)
            )
            if self.neurons
            else 0,
            "memory_usage_estimate": len(str(self.neurons)) / (1024 * 1024),
            "last_update": datetime.now().isoformat(),
        }


def logit(x: float) -> float:
    """邏輯轉換函數"""
    x = max(0.001, min(x, 0.999))
    return math.log(x / (1 - x))


if __name__ == "__main__":
    # 使用示例
    index = EnhancedNeuralIndex(dimensions=768)

    # 添加示例文檔
    test_docs = [
        ("doc1", "這是關於 Python 最佳實踐的文檔"),
        ("doc2", "本地 AI 模型優化指南"),
        ("doc3", "分佈式系統設計模式"),
    ]

    for doc_id, content in test_docs:
        neuron_id = index.add_document(doc_id, content)
        print(f"✅ 添加文檔: {neuron_id}")

    query = "Python 優化"
    query_embedding = index.embed_query(query)
    results = index.retrieve(query_embedding, top_k=3)

    print("\n📊 檢索結果:")
    for result in results:
        print(f"  - {result['doc_id']}: {result['similarity']:.4f}")

    # 保存索引
    index.save_index()

    # 顯示統計
    stats = index.get_stats()
    print("\n📈 索引統計:")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
