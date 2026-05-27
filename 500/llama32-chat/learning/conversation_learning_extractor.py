#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
對話學習提取器 (Conversation Learning Extractor)
從對話記憶中提取關鍵信息，讓本地模型學習
支持跨模型學習：從 Gemini/Claude/OpenAI 的對話反推本地模型學習

核心功能：
1. 自動從對話中提取知識點
2. 按優先級分類對話
3. 轉換為本地模型可學習的格式
4. 實現反向學習：其他模型 → 本地模型知識庫
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib


class ConversationLearningExtractor:
    """從對話記憶中提取和轉化學習內容"""

    def __init__(self, conversations_file: str, output_dir: str = "data/learning"):
        self.conversations_file = Path(conversations_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 輸出文件
        self.extracted_knowledge_file = self.output_dir / "extracted_knowledge.json"
        self.learning_patterns_file = self.output_dir / "learning_patterns.json"
        self.cross_model_insights_file = self.output_dir / "cross_model_insights.json"
        self.adaptive_training_data_file = (
            self.output_dir / "adaptive_training_data.json"
        )

        # 知識提取規則
        self.extraction_patterns = {
            "代碼示例": r"```[\w]*\n([\s\S]*?)```",
            "概念解釋": r"【(.+?)】|###\s+(.+?)$",
            "最佳實踐": r"✅|最佳實踐|推薦|建議",
            "常見錯誤": r"❌|常見錯誤|陷阱|注意",
            "性能優化": r"性能|優化|快速|效率",
            "安全相關": r"安全|隱私|身份驗證|加密",
        }

        self.priority_keywords = {
            "critical": ["安全", "錯誤", "失敗", "崩潰", "攻擊"],
            "high": ["性能", "最佳實踐", "架構", "設計模式"],
            "medium": ["功能", "特性", "工具", "方法"],
            "low": ["觀點", "建議", "讚賞", "感謝"],
        }

    def extract_all_knowledge(self) -> Dict[str, Any]:
        """從所有對話中提取知識"""
        print("🧠 開始提取對話知識...")

        conversations = self._load_conversations()
        if not conversations:
            print("❌ 無法加載對話記錄")
            return {}

        # 提取知識
        all_knowledge = {
            "timestamp": datetime.now().isoformat(),
            "total_conversations_analyzed": len(conversations),
            "knowledge_extracted": [],
            "patterns_found": defaultdict(list),
            "cross_model_learning": {},
            "quality_metrics": {},
        }

        for conv in conversations:
            knowledge = self._extract_from_conversation(conv)
            if knowledge:
                all_knowledge["knowledge_extracted"].extend(knowledge)

                # 按來源模型分組
                source_model = conv.get("source", "unknown")
                if source_model not in all_knowledge["cross_model_learning"]:
                    all_knowledge["cross_model_learning"][source_model] = {
                        "conversations": 0,
                        "knowledge_count": 0,
                        "total_messages": 0,
                    }

                all_knowledge["cross_model_learning"][source_model][
                    "conversations"
                ] += 1
                all_knowledge["cross_model_learning"][source_model][
                    "knowledge_count"
                ] += len(knowledge)
                all_knowledge["cross_model_learning"][source_model][
                    "total_messages"
                ] += len(conv.get("messages", []))

        # 計算質量指標
        all_knowledge["quality_metrics"] = self._calculate_quality_metrics(
            all_knowledge["knowledge_extracted"]
        )

        # 保存提取結果
        self._save_json(self.extracted_knowledge_file, all_knowledge)

        print(f"✅ 提取完成: {len(all_knowledge['knowledge_extracted'])} 個知識點")
        print(f"   來自 {len(all_knowledge['cross_model_learning'])} 個模型源")

        return all_knowledge

    def _extract_from_conversation(
        self, conversation: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """從單個對話中提取知識"""
        knowledge_list = []
        messages = conversation.get("messages", [])

        for i, message in enumerate(messages):
            if message.get("role") == "assistant":
                # 提取多種類型的知識
                extracted = {
                    "conversation_id": conversation.get("id"),
                    "source": conversation.get("source", "unknown"),
                    "timestamp": message.get("timestamp"),
                    "content_hash": hashlib.md5(
                        message.get("content", "").encode()
                    ).hexdigest(),
                    "knowledge_items": [],
                }

                content = message.get("content", "")

                # 提取代碼示例
                code_matches = re.findall(self.extraction_patterns["代碼示例"], content)
                if code_matches:
                    extracted["knowledge_items"].append(
                        {
                            "type": "code_example",
                            "count": len(code_matches),
                            "has_code": True,
                            "quality_score": self._score_code_quality(code_matches),
                        }
                    )

                # 提取概念解釋
                concept_matches = re.findall(
                    self.extraction_patterns["概念解釋"], content
                )
                if concept_matches:
                    extracted["knowledge_items"].append(
                        {
                            "type": "concept",
                            "concepts": [c[0] or c[1] for c in concept_matches],
                            "count": len(concept_matches),
                        }
                    )

                # 提取最佳實踐
                if re.search(self.extraction_patterns["最佳實踐"], content):
                    extracted["knowledge_items"].append(
                        {
                            "type": "best_practice",
                            "found": True,
                            "text_length": len(content),
                        }
                    )

                # 提取常見錯誤
                if re.search(self.extraction_patterns["常見錯誤"], content):
                    extracted["knowledge_items"].append(
                        {"type": "common_mistakes", "found": True}
                    )

                # 優先級判定
                extracted["priority"] = self._determine_priority(content)

                # 相關性分析
                extracted["relevance_to_local_model"] = self._analyze_relevance(
                    content, conversation.get("tags", [])
                )

                if extracted["knowledge_items"]:
                    knowledge_list.append(extracted)

        return knowledge_list

    def _determine_priority(self, content: str) -> str:
        """根據內容確定優先級"""
        for priority, keywords in self.priority_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    return priority
        return "low"

    def _analyze_relevance(self, content: str, tags: List[str]) -> float:
        """分析內容對本地模型的相關性 (0-1)"""
        relevance = 0.5  # 基礎相關性

        # 標籤相關性增加
        local_relevant_tags = [
            "code",
            "programming",
            "learning",
            "local",
            "optimization",
        ]
        relevance += len([t for t in tags if t in local_relevant_tags]) * 0.1

        # 內容特徵增加相關性
        features = {
            "本地": 0.2,
            "離線": 0.2,
            "最佳實踐": 0.15,
            "優化": 0.15,
            "架構": 0.1,
        }

        for feature, score in features.items():
            if feature in content:
                relevance += score

        return min(relevance, 1.0)

    def _score_code_quality(self, code_samples: List[str]) -> float:
        """評分代碼示例的質量"""
        if not code_samples:
            return 0.0

        total_score = 0
        for code in code_samples:
            # 評估代碼長度
            length_score = min(len(code) / 500, 1.0)
            # 評估結構性
            structure_score = (
                1.0 if "{" in code or "def " in code or "class " in code else 0.5
            )
            total_score += (length_score + structure_score) / 2

        return total_score / len(code_samples)

    def _calculate_quality_metrics(self, knowledge_items: List[Dict]) -> Dict[str, Any]:
        """計算提取知識的質量指標"""
        if not knowledge_items:
            return {}

        metrics = {
            "total_items": len(knowledge_items),
            "average_priority": self._calculate_avg_priority(knowledge_items),
            "relevance_distribution": self._calculate_relevance_distribution(
                knowledge_items
            ),
            "knowledge_type_distribution": self._calculate_type_distribution(
                knowledge_items
            ),
            "code_examples_found": sum(
                1
                for k in knowledge_items
                for item in k.get("knowledge_items", [])
                if item.get("type") == "code_example"
            ),
            "best_practices_found": sum(
                1
                for k in knowledge_items
                for item in k.get("knowledge_items", [])
                if item.get("type") == "best_practice"
            ),
        }

        return metrics

    def _calculate_avg_priority(self, items: List[Dict]) -> float:
        """計算平均優先級指數"""
        priority_scores = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        if not items:
            return 0

        scores = [priority_scores.get(item.get("priority", "low"), 1) for item in items]
        return sum(scores) / len(scores)

    def _calculate_relevance_distribution(self, items: List[Dict]) -> Dict:
        """計算相關性分佈"""
        relevances = [item.get("relevance_to_local_model", 0) for item in items]
        if not relevances:
            return {}

        return {
            "min": min(relevances),
            "max": max(relevances),
            "average": sum(relevances) / len(relevances),
            "high_relevance_count": sum(1 for r in relevances if r > 0.7),
            "medium_relevance_count": sum(1 for r in relevances if 0.4 < r <= 0.7),
            "low_relevance_count": sum(1 for r in relevances if r <= 0.4),
        }

    def _calculate_type_distribution(self, items: List[Dict]) -> Dict[str, int]:
        """計算知識類型分佈"""
        distribution = defaultdict(int)
        for item in items:
            for knowledge_item in item.get("knowledge_items", []):
                distribution[knowledge_item.get("type", "unknown")] += 1

        return dict(distribution)

    def generate_training_data_for_local_model(self) -> Dict[str, Any]:
        """生成可直接用於本地模型訓練的數據"""
        print("\n🎓 生成本地模型訓練數據...")

        knowledge = self._load_json(self.extracted_knowledge_file)
        if not knowledge:
            knowledge = self.extract_all_knowledge()

        training_data = {
            "timestamp": datetime.now().isoformat(),
            "training_examples": [],
            "instruction_pairs": [],
            "knowledge_base_entries": [],
            "learning_priorities": [],
        }

        for know in knowledge.get("knowledge_extracted", []):
            # 轉換為訓練示例
            example = self._convert_to_training_example(know)
            if example:
                training_data["training_examples"].append(example)

                # 高優先級項目
                if know.get("priority") in ["critical", "high"]:
                    training_data["learning_priorities"].append(
                        {
                            "source": know.get("source"),
                            "conversation_id": know.get("conversation_id"),
                            "priority": know.get("priority"),
                            "timestamp": know.get("timestamp"),
                        }
                    )

        # 保存訓練數據
        self._save_json(self.adaptive_training_data_file, training_data)

        print(f"✅ 生成 {len(training_data['training_examples'])} 個訓練示例")

        return training_data

    def _convert_to_training_example(
        self, knowledge_item: Dict[str, Any]
    ) -> Optional[Dict]:
        """將知識項轉換為訓練示例"""
        if not knowledge_item.get("knowledge_items"):
            return None

        return {
            "conversation_id": knowledge_item.get("conversation_id"),
            "source_model": knowledge_item.get("source"),
            "priority": knowledge_item.get("priority"),
            "relevance_score": knowledge_item.get("relevance_to_local_model"),
            "knowledge_items": knowledge_item.get("knowledge_items"),
            "timestamp": knowledge_item.get("timestamp"),
            "learning_value": self._calculate_learning_value(knowledge_item),
        }

    def _calculate_learning_value(self, item: Dict[str, Any]) -> float:
        """計算該項對本地模型的學習價值"""
        value = 0.0

        # 優先級貢獻
        priority_weights = {"critical": 0.4, "high": 0.3, "medium": 0.2, "low": 0.1}
        value += priority_weights.get(item.get("priority", "low"), 0.1)

        # 相關性貢獻
        value += item.get("relevance_to_local_model", 0) * 0.4

        # 知識類型貢獻
        knowledge_types = item.get("knowledge_items", [])
        if any(k.get("type") == "code_example" for k in knowledge_types):
            value += 0.2  # 代碼示例很有價值

        return min(value, 1.0)

    def _load_conversations(self) -> List[Dict]:
        """加載對話記錄"""
        try:
            return self._load_json(self.conversations_file)
        except Exception as e:
            print(f"❌ 加載對話失敗: {e}")
            return []

    def _load_json(self, path: Path) -> Any:
        """安全加載 JSON"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 加載 JSON 失敗 ({path}): {e}")
            return None

    def _save_json(self, path: Path, data: Any):
        """安全保存 JSON"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存 JSON 失敗 ({path}): {e}")

    def get_summary(self) -> Dict[str, Any]:
        """獲取提取摘要"""
        knowledge = self._load_json(self.extracted_knowledge_file)
        if not knowledge:
            return {"status": "no_data"}

        return {
            "status": "extracted",
            "total_conversations": knowledge.get("total_conversations_analyzed"),
            "knowledge_items": len(knowledge.get("knowledge_extracted", [])),
            "cross_model_sources": list(
                knowledge.get("cross_model_learning", {}).keys()
            ),
            "quality_metrics": knowledge.get("quality_metrics"),
            "last_extraction": knowledge.get("timestamp"),
        }


if __name__ == "__main__":
    # 使用示例（相對本專案 llama32-chat/data）
    _llama_root = Path(__file__).resolve().parent.parent
    extractor = ConversationLearningExtractor(
        conversations_file=str(_llama_root / "data" / "conversations.json")
    )

    # 提取所有知識
    knowledge = extractor.extract_all_knowledge()

    # 生成訓練數據
    training_data = extractor.generate_training_data_for_local_model()

    # 顯示摘要
    summary = extractor.get_summary()
    print("\n📊 提取摘要:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
