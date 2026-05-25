#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體自主學習系統 - 升級版
包含進階學習算法和性能優化
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict
import re

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "tools"))

from local_memory_api import LocalMemoryAPI


class AgentSelfLearningEnhanced:
    """增強版智能體自主學習系統"""

    def __init__(self):
        self.base_dir = BASE_DIR
        self.memory_api = LocalMemoryAPI(str(self.base_dir))
        self.learning_config = {
            "min_confidence": 0.7,
            "max_context_depth": 10,
            "learning_rate": 0.01,
            "batch_size": 32,
            "enable_online_learning": True,
        }

        self.domain_weights = {
            "AI/機器學習": 1.5,
            "系統設計": 1.4,
            "安全": 1.5,
            "性能優化": 1.4,
            "默認": 1.0,
        }

    def advanced_analyze(self, limit: int = 50) -> Dict:
        """進階分析"""
        print("\n智能體自主學習分析 - 升級版")
        print("=" * 40)

        all_convs = self.memory_api.get_all_conversations()

        if not all_convs:
            print("無法加載對話")
            return None

        messages = []
        if isinstance(all_convs, list):
            for conv in all_convs:
                if isinstance(conv, dict):
                    if "messages" in conv and isinstance(conv["messages"], list):
                        messages.extend(conv["messages"])

        recent_messages = messages[-limit:] if len(messages) > limit else messages

        print(f"已加載 {len(recent_messages)} 條對話")

        return self._deep_analyze(recent_messages)

    def _deep_analyze(self, messages) -> Dict:
        """深度分析"""
        user_msgs = [
            m for m in messages if isinstance(m, dict) and m.get("role") == "user"
        ]
        assistant_msgs = [
            m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"
        ]

        print(f"用戶提問: {len(user_msgs)} 次")
        print(f"助手回應: {len(assistant_msgs)} 次")

        domain_analysis = self._analyze_domains(messages)

        print("\n領域分析:")
        for domain, score in sorted(
            domain_analysis.items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  {domain}: {score:.2f}")

        return {"messages_count": len(messages), "domain_analysis": domain_analysis}

    def _analyze_domains(self, messages) -> Dict:
        """分析領域"""
        domain_keywords = {
            "AI/機器學習": ["ai", "machine learning", "model", "neural", "深度學習"],
            "系統設計": ["system", "architecture", "design", "系統", "架構"],
            "安全": ["security", "安全", "漏洞", "加密"],
            "性能優化": ["performance", "優化", "效率"],
        }

        domain_scores = {domain: 0 for domain in domain_keywords}

        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "").lower()
                for domain, keywords in domain_keywords.items():
                    for keyword in keywords:
                        if keyword.lower() in content:
                            domain_scores[domain] += self.domain_weights.get(
                                domain, 1.0
                            )

        return domain_scores


if __name__ == "__main__":
    learning = AgentSelfLearningEnhanced()
    learning.advanced_analyze()
