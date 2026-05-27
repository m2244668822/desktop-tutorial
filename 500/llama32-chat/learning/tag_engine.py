#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
標籤引擎 (Tag Engine)
自動為知識片段、對話、任務、學習目標打標籤。

功能：
  1. TagTaxonomy   — 維護動態標籤分類體系（自動成長）
  2. AutoTagger    — 規則 + 統計雙引擎，自動標記文字
  3. TagIndex      — 倒排索引，支援按標籤快速查詢
  4. TagEngine     — 對外統一介面

標籤分層結構：
  domain/     → 主題領域 (ai, python, web, learning, task, user, system…)
  type/       → 內容類型 (conversation, task, error, insight, goal…)
  sentiment/  → 情感 (positive, negative, neutral, urgent)
  skill/      → 技能層級 (beginner, intermediate, advanced)
  status/     → 狀態 (open, resolved, learning, done)
"""

import json
import re
import time
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT = _THIS_DIR.parent
_DATA_DIR = _PROJECT / "data"
_TAG_DIR = _DATA_DIR / "tags"


def _load(path: Path, default=None):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default if default is not None else {}


def _save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 1. TagTaxonomy — 動態標籤分類體系
# ═══════════════════════════════════════════════════════════════


class TagTaxonomy:
    """
    維護全域標籤清單與使用統計。
    每次打標籤後自動記錄頻率，讓高頻標籤更容易被發現。
    """

    FILE = _TAG_DIR / "taxonomy.json"

    # 內建種子標籤（保證基礎覆蓋）
    _SEEDS: Dict[str, List[str]] = {
        "domain": [
            "ai",
            "machine_learning",
            "deep_learning",
            "nlp",
            "python",
            "flask",
            "web",
            "api",
            "database",
            "agent",
            "orchestrator",
            "learning",
            "autonomy",
            "collaboration",
            "system",
            "performance",
            "security",
            "user_interface",
            "data_analysis",
            "task_management",
        ],
        "type": [
            "conversation",
            "task",
            "error",
            "insight",
            "goal",
            "knowledge",
            "feedback",
            "code",
            "config",
        ],
        "sentiment": ["positive", "negative", "neutral", "urgent"],
        "skill": ["beginner", "intermediate", "advanced"],
        "status": ["open", "resolved", "learning", "done", "pending"],
        "priority": ["high", "medium", "low"],
    }

    def __init__(self):
        stored = _load(self.FILE, {})
        # tags: { "full_tag": count }
        self.tags: Dict[str, int] = stored.get("tags", {})
        # 確保種子標籤存在
        for category, labels in self._SEEDS.items():
            for label in labels:
                full = f"{category}/{label}"
                self.tags.setdefault(full, 0)
        self._dirty = False

    def record(self, tags: List[str]):
        """記錄一批標籤被使用（增加計數）。"""
        for tag in tags:
            self.tags[tag] = self.tags.get(tag, 0) + 1
        self._dirty = True

    def add_custom(self, category: str, label: str) -> str:
        """動態新增自訂標籤，回傳完整標籤名。"""
        full = f"{category}/{label.lower().replace(' ', '_')}"
        self.tags.setdefault(full, 0)
        self._dirty = True
        return full

    def top_tags(self, category: str = None, n: int = 20) -> List[Tuple[str, int]]:
        """回傳最常用的 n 個標籤（可過濾分類）。"""
        if category:
            items = [
                (t, c) for t, c in self.tags.items() if t.startswith(f"{category}/")
            ]
        else:
            items = list(self.tags.items())
        return sorted(items, key=lambda x: x[1], reverse=True)[:n]

    def flush(self):
        if self._dirty:
            _save(
                self.FILE, {"tags": self.tags, "updated_at": datetime.now().isoformat()}
            )
            self._dirty = False


# ═══════════════════════════════════════════════════════════════
# 2. AutoTagger — 自動標記引擎（規則 + 統計）
# ═══════════════════════════════════════════════════════════════


class AutoTagger:
    """
    給任意文字自動打上多層標籤。
    使用規則字典 + TF 統計雙引擎。
    """

    # 關鍵字 → 標籤 對應規則
    _RULES: Dict[str, List[str]] = {
        # domain
        r"python|def |import |class |\.py": ["domain/python"],
        r"flask|route|endpoint|api|http|request|response": [
            "domain/flask",
            "domain/api",
            "domain/web",
        ],
        r"sql|database|sqlite|orm|query|select|insert|table": ["domain/database"],
        r"agent|智能體|協作|orchestrat": ["domain/agent", "domain/orchestrator"],
        r"學習|learn|training|model|neural|rag|embed": ["domain/learning", "domain/ai"],
        r"error|exception|fail|traceback|bug|crash|錯誤|失敗": [
            "type/error",
            "sentiment/negative",
        ],
        r"task|任務|job|schedule|queue|priority": [
            "type/task",
            "domain/task_management",
        ],
        r"insight|洞察|pattern|發現|discover": ["type/insight"],
        r"feedback|回饋|rating|評分|評價": ["type/feedback"],
        r"urgent|緊急|critical|asap|立刻|馬上": ["sentiment/urgent", "priority/high"],
        r"success|完成|done|solved|ok|正確|成功": [
            "sentiment/positive",
            "status/resolved",
        ],
        r"user|用戶|使用者|互動|interaction": ["domain/user_interface"],
        r"performance|速度|latency|timeout|slow|快|慢": ["domain/performance"],
        r"security|安全|auth|token|password|金鑰|密碼": ["domain/security"],
        r"config|配置|設定|env|環境變數|\.env": ["domain/config", "type/config"],
        r"collaboration|協同|共享|share|委派|delegate": ["domain/collaboration"],
        r"tag|標籤|label|分類|classify": ["domain/system"],
        r"goal|目標|objective|plan|計劃": ["type/goal"],
        r"knowledge|知識|資料|data|information": ["type/knowledge"],
    }

    def __init__(self, taxonomy: TagTaxonomy):
        self.taxonomy = taxonomy
        # 預編譯 regex
        self._compiled = [
            (re.compile(pattern, re.IGNORECASE), tags)
            for pattern, tags in self._RULES.items()
        ]

    def tag(self, text: str, extra_context: Dict[str, str] = None) -> List[str]:
        """
        對文字進行自動標記。
        extra_context: {"type": "task", "status": "completed"} 等預設值
        回傳去重後的標籤清單。
        """
        found: Set[str] = set()

        # 規則匹配
        for pattern, tags in self._compiled:
            if pattern.search(text):
                found.update(tags)

        # 預設 context 標籤
        if extra_context:
            for category, label in extra_context.items():
                if label:
                    found.add(f"{category}/{label.lower()}")

        # 長文字加 advanced，短文字加 beginner
        if len(text) > 500:
            found.add("skill/advanced")
        elif len(text) < 80:
            found.add("skill/beginner")
        else:
            found.add("skill/intermediate")

        # 若無情感標籤，預設 neutral
        has_sentiment = any(t.startswith("sentiment/") for t in found)
        if not has_sentiment:
            found.add("sentiment/neutral")

        result = sorted(found)
        self.taxonomy.record(result)
        return result

    def tag_item(
        self,
        item: Dict[str, Any],
        text_fields: List[str],
        context: Dict[str, str] = None,
    ) -> List[str]:
        """
        對 dict 物件中指定欄位的文字自動標記。
        item: 要標記的資料物件
        text_fields: 要提取文字的欄位名清單
        context: 額外的預設分類
        """
        combined_text = " ".join(str(item.get(f, "") or "") for f in text_fields)
        return self.tag(combined_text, extra_context=context)


# ═══════════════════════════════════════════════════════════════
# 3. TagIndex — 倒排索引
# ═══════════════════════════════════════════════════════════════


class TagIndex:
    """
    倒排索引：tag → [item_id, ...]
    支援多標籤 AND / OR 查詢。
    """

    FILE = _TAG_DIR / "tag_index.json"

    def __init__(self):
        stored = _load(self.FILE, {})
        # { "domain/python": ["id1", "id2", ...] }
        self._index: Dict[str, List[str]] = stored.get("index", {})
        self._item_tags: Dict[str, List[str]] = stored.get("item_tags", {})
        self._dirty = False

    def index_item(self, item_id: str, tags: List[str]):
        """為一個 item 建立索引。"""
        # 先移除舊索引
        old_tags = self._item_tags.get(item_id, [])
        for tag in old_tags:
            if tag in self._index and item_id in self._index[tag]:
                self._index[tag].remove(item_id)

        # 建立新索引
        self._item_tags[item_id] = tags
        for tag in tags:
            self._index.setdefault(tag, [])
            if item_id not in self._index[tag]:
                self._index[tag].append(item_id)
        self._dirty = True

    def query_and(self, tags: List[str]) -> List[str]:
        """回傳同時擁有所有 tags 的 item_id 清單。"""
        if not tags:
            return []
        sets = [set(self._index.get(tag, [])) for tag in tags]
        result = sets[0]
        for s in sets[1:]:
            result &= s
        return sorted(result)

    def query_or(self, tags: List[str]) -> List[str]:
        """回傳擁有任意一個 tag 的 item_id 清單。"""
        result: Set[str] = set()
        for tag in tags:
            result |= set(self._index.get(tag, []))
        return sorted(result)

    def get_tags(self, item_id: str) -> List[str]:
        """取得一個 item 的所有標籤。"""
        return self._item_tags.get(item_id, [])

    def tag_stats(self) -> Dict[str, int]:
        """回傳每個 tag 的索引數量。"""
        return {tag: len(ids) for tag, ids in self._index.items()}

    def flush(self):
        if self._dirty:
            _save(
                self.FILE,
                {
                    "index": self._index,
                    "item_tags": self._item_tags,
                    "updated_at": datetime.now().isoformat(),
                },
            )
            self._dirty = False


# ═══════════════════════════════════════════════════════════════
# 4. TagEngine — 對外統一介面
# ═══════════════════════════════════════════════════════════════


class TagEngine:
    """
    統一標籤操作介面。
    - tag_text(text)         → 對純文字打標籤
    - tag_conversation(conv) → 對對話物件打標籤並建立索引
    - tag_task(task)         → 對任務物件打標籤並建立索引
    - tag_knowledge(fragment)→ 對知識片段打標籤並建立索引
    - search(tags)           → 按標籤查詢
    - top_tags()             → 最熱門標籤
    - flush()                → 寫入磁碟
    """

    TAGGED_KNOWLEDGE_FILE = _TAG_DIR / "tagged_knowledge.json"

    def __init__(self):
        self.taxonomy = TagTaxonomy()
        self.tagger = AutoTagger(self.taxonomy)
        self.index = TagIndex()
        # 已標記知識快取 { item_id: {tags, content, …} }
        self._knowledge: Dict[str, Dict] = _load(self.TAGGED_KNOWLEDGE_FILE, {})

    # ── 標記入口 ──────────────────────────────────────────────

    def tag_text(self, text: str, context: Dict[str, str] = None) -> List[str]:
        """對純文字打標籤（不建立索引）。"""
        return self.tagger.tag(text, extra_context=context)

    def tag_conversation(self, conv: Dict) -> List[str]:
        """對對話物件打標籤並加入索引。"""
        item_id = str(conv.get("id") or conv.get("timestamp") or id(conv))
        tags = self.tagger.tag_item(
            conv,
            text_fields=["prompt", "user_message", "response", "content"],
            context={"type": "conversation"},
        )
        self.index.index_item(item_id, tags)
        return tags

    def tag_task(self, task: Dict) -> List[str]:
        """對任務物件打標籤並加入索引。"""
        item_id = str(task.get("id") or task.get("title") or id(task))
        status = task.get("status", "pending")
        tags = self.tagger.tag_item(
            task,
            text_fields=["title", "description", "prompt", "result"],
            context={"type": "task", "status": status},
        )
        self.index.index_item(item_id, tags)
        return tags

    def tag_knowledge(self, fragment: Dict, knowledge_id: str = None) -> List[str]:
        """對知識片段打標籤並儲存。"""
        item_id = knowledge_id or str(fragment.get("goal_id") or id(fragment))
        text = " ".join(
            f.get("content", "") for f in fragment.get("fragments", [])
        ) or fragment.get("query", "")
        tags = self.tagger.tag(text, extra_context={"type": "knowledge"})
        self.index.index_item(item_id, tags)

        self._knowledge[item_id] = {
            "query": fragment.get("query", ""),
            "tags": tags,
            "fragment_count": len(fragment.get("fragments", [])),
            "tagged_at": datetime.now().isoformat(),
        }
        return tags

    def tag_goal(self, goal: Dict) -> List[str]:
        """對學習目標打標籤。"""
        item_id = str(goal.get("id") or id(goal))
        tags = self.tagger.tag_item(
            goal,
            text_fields=["query", "type", "source"],
            context={"type": "goal", "status": goal.get("status", "pending")},
        )
        self.index.index_item(item_id, tags)
        return tags

    # ── 查詢介面 ──────────────────────────────────────────────

    def search(self, tags: List[str], mode: str = "or") -> List[str]:
        """
        按標籤搜尋，回傳 item_id 清單。
        mode: "and" = 全部符合；"or" = 任一符合
        """
        if mode == "and":
            return self.index.query_and(tags)
        return self.index.query_or(tags)

    def get_tags(self, item_id: str) -> List[str]:
        return self.index.get_tags(item_id)

    def top_tags(self, category: str = None, n: int = 15) -> List[Tuple[str, int]]:
        return self.taxonomy.top_tags(category, n)

    def tag_stats(self) -> Dict[str, Any]:
        """回傳標籤統計摘要，供 API 使用。"""
        index_stats = self.index.tag_stats()
        top = self.taxonomy.top_tags(n=10)
        return {
            "total_tags": len(self.taxonomy.tags),
            "indexed_items": len(self.index._item_tags),
            "top_tags": [{"tag": t, "count": c} for t, c in top],
            "index_stats": dict(
                sorted(index_stats.items(), key=lambda x: x[1], reverse=True)[:20]
            ),
        }

    # ── 批次標記 ──────────────────────────────────────────────

    def bulk_tag_conversations(self, conversations: List[Dict]) -> int:
        """批次標記對話列表，回傳新增標記數。"""
        count = 0
        for conv in conversations:
            self.tag_conversation(conv)
            count += 1
        return count

    def bulk_tag_tasks(self, tasks: List[Dict]) -> int:
        """批次標記任務列表。"""
        count = 0
        for task in tasks:
            self.tag_task(task)
            count += 1
        return count

    # ── 持久化 ────────────────────────────────────────────────

    def flush(self):
        """將所有索引寫入磁碟。"""
        self.taxonomy.flush()
        self.index.flush()
        _save(self.TAGGED_KNOWLEDGE_FILE, self._knowledge)
