#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自主學習協調器 (Autonomous Learning Orchestrator)
架構：協調器迴圈疊加在 UnifiedLearningHub 之上

功能：
  1. InteractionProfiler   — 分析用戶互動偏好，建立溝通風格模型
  2. LearningGoalEngine    — 自主評估知識缺口，產生下一輪學習目標
  3. DataSeeker            — 主動從對話記錄/任務/檔案系統/外部 API 蒐集資料
  4. AutonomousLearningOrchestrator — 協調器主迴圈，驅動以上三個模組持續運作

設計原則：
  - 零人工觸發：伺服器啟動後自行運作，無需用戶下指令
  - 回饋閉環：學習結果 → 調整互動策略 → 產生新目標 → 再學習
  - 非侵入性：以 daemon thread 運行，不影響主伺服器回應速度
"""

import json
import logging
import math
import os
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("autonomous_learning_orchestrator")

# ── 延遲載入新模組（避免啟動時失敗中斷整個 server）──────────


def _try_import_distiller():
    try:
        from knowledge_distiller import KnowledgeDistiller

        return KnowledgeDistiller()
    except Exception as e:
        logger.warning("[Orchestrator] KnowledgeDistiller 未載入: %s", e)
        return None


def _try_import_validator():
    try:
        from knowledge_validator import KnowledgeValidator

        return KnowledgeValidator()
    except Exception as e:
        logger.warning("[Orchestrator] KnowledgeValidator 未載入: %s", e)
        return None


def _try_import_comms():
    """載入 agent_communication 全域 broker + registry。"""
    try:
        import sys as _sys

        _agents_dir = str(Path(__file__).resolve().parent.parent / "agents")
        _project_dir = str(Path(__file__).resolve().parent.parent)
        for d in (_agents_dir, _project_dir):
            if d not in _sys.path:
                _sys.path.insert(0, d)
        from agent_communication import (
            message_broker,
            agent_registry,
            EventType,
            Message,
        )

        return message_broker, agent_registry, EventType, Message
    except Exception as e:
        logger.warning("[Orchestrator] agent_communication 未載入: %s", e)
        return None, None, None, None


# ─────────────────────────────────────────────
# 路徑解析（相對於本檔案位置）
# ─────────────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent  # learning/
_PROJECT_ROOT = _THIS_DIR.parent  # llama32-chat/
_DATA_DIR = _PROJECT_ROOT / "data"
_LOGS_DIR = _PROJECT_ROOT / "logs"


def _load_json(path: Path, default=None):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug("無法讀取 %s: %s", path, e)
    return default if default is not None else {}


def _save_json(path: Path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("無法儲存 %s: %s", path, e)


# ═══════════════════════════════════════════════════════════════
# 1. InteractionProfiler — 用戶互動偏好分析器
# ═══════════════════════════════════════════════════════════════


class InteractionProfiler:
    """
    分析用戶互動模式，建立溝通風格模型。
    讀取對話記錄，推斷：
      - 常用主題
      - 偏好的回應詳細程度
      - 活躍時段
      - 任務成功/失敗傾向
    """

    PROFILE_FILE = _DATA_DIR / "interaction_profile.json"

    def __init__(self):
        self.profile: Dict[str, Any] = _load_json(
            self.PROFILE_FILE,
            {
                "topics": {},
                "style": {
                    "avg_message_len": 0,
                    "prefers_detail": False,
                    "uses_code": False,
                    "language": "zh-TW",
                },
                "active_hours": {},
                "task_patterns": {
                    "most_requested": [],
                    "success_rate": 1.0,
                },
                "last_updated": None,
            },
        )

    # ── 主要更新入口 ──────────────────────────────────────────

    def update(self, conversations: List[Dict], tasks: List[Dict]) -> Dict:
        """從最新對話和任務記錄更新用戶偏好檔案。"""
        self._update_topics(conversations)
        self._update_style(conversations)
        self._update_active_hours(conversations)
        self._update_task_patterns(tasks)
        self.profile["last_updated"] = datetime.now().isoformat()
        _save_json(self.PROFILE_FILE, self.profile)
        logger.info(
            "[Profiler] 互動偏好已更新，主要主題: %s", list(self.profile["topics"])[:5]
        )
        return self.profile

    # ── 私有分析方法 ──────────────────────────────────────────

    def _update_topics(self, conversations: List[Dict]):
        topic_counter = Counter(self.profile.get("topics", {}))
        # 優先使用有內容的對話
        valid_convs = [
            c
            for c in conversations
            if (c.get("prompt") or c.get("user_message") or "").strip()
        ]
        if not valid_convs:
            # 若對話全空，改從 response 欄位提取
            valid_convs = [
                c for c in conversations if (c.get("response") or "").strip()
            ]
        keywords = self._extract_keywords(valid_convs)
        # 補充：從 learning_log 讀取主題
        ll_file = _DATA_DIR / "learning_log.json"
        ll = _load_json(ll_file, [])
        for entry in ll:
            task_text = str(entry.get("task") or entry.get("topic") or "")
            for tok in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][a-z]{2,}", task_text):
                if len(tok) >= 2:
                    keywords.append(tok.lower())
        for kw in keywords:
            topic_counter[kw] += 1
        top = dict(topic_counter.most_common(50))
        self.profile["topics"] = top

    def _update_style(self, conversations: List[Dict]):
        lengths = []
        code_count = 0
        for conv in conversations[-100:]:
            msg = conv.get("prompt", "") or conv.get("user_message", "")
            if not msg:
                continue
            lengths.append(len(msg))
            if "```" in msg or "def " in msg or "import " in msg:
                code_count += 1
        if lengths:
            avg = sum(lengths) / len(lengths)
            self.profile["style"]["avg_message_len"] = round(avg)
            self.profile["style"]["prefers_detail"] = avg > 80
            self.profile["style"]["uses_code"] = code_count > len(lengths) * 0.15

    def _update_active_hours(self, conversations: List[Dict]):
        hour_counter: Dict[str, int] = defaultdict(int)
        for conv in conversations:
            ts = conv.get("timestamp") or conv.get("created_at") or ""
            try:
                dt = datetime.fromisoformat(ts[:19])
                hour_counter[str(dt.hour)] += 1
            except Exception:
                pass
        self.profile["active_hours"] = dict(hour_counter)

    def _update_task_patterns(self, tasks: List[Dict]):
        if not tasks:
            return
        titles = [t.get("title", "") for t in tasks[-50:] if t.get("title")]
        completed = [t for t in tasks if t.get("status") == "completed"]
        total = len(tasks)
        rate = len(completed) / total if total else 1.0
        # 提取常見任務類型關鍵字
        kw_counter: Counter = Counter()
        for title in titles:
            for word in re.findall(r"[\w\u4e00-\u9fff]{2,}", title):
                kw_counter[word] += 1
        self.profile["task_patterns"]["most_requested"] = [
            w for w, _ in kw_counter.most_common(10)
        ]
        self.profile["task_patterns"]["success_rate"] = round(rate, 3)

    @staticmethod
    def _extract_keywords(conversations: List[Dict]) -> List[str]:
        """從對話文字中提取關鍵詞（中英混合）。"""
        text_blob = " ".join(
            (conv.get("prompt") or conv.get("user_message") or "")
            for conv in conversations[-200:]
        )
        tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", text_blob)
        stop = {
            "的",
            "了",
            "是",
            "在",
            "我",
            "你",
            "他",
            "她",
            "它",
            "我們",
            "你們",
            "他們",
            "這",
            "那",
            "有",
            "和",
            "or",
            "the",
            "is",
            "a",
            "an",
            "to",
            "for",
            "with",
            "and",
            "this",
            "that",
            "it",
            "be",
            "at",
            "by",
        }
        return [t.lower() for t in tokens if t not in stop and len(t) >= 2]

    # ── 查詢介面 ──────────────────────────────────────────────

    def get_top_topics(self, n: int = 10) -> List[str]:
        return sorted(
            self.profile.get("topics", {}),
            key=lambda k: self.profile["topics"][k],
            reverse=True,
        )[:n]

    def get_style_hint(self) -> str:
        style = self.profile.get("style", {})
        hints = []
        if style.get("prefers_detail"):
            hints.append("詳細說明")
        else:
            hints.append("簡潔回答")
        if style.get("uses_code"):
            hints.append("含程式碼範例")
        return "、".join(hints) if hints else "一般"

    def get_peak_hour(self) -> Optional[int]:
        hours = self.profile.get("active_hours", {})
        if not hours:
            return None
        return int(max(hours, key=lambda h: hours[h]))


# ═══════════════════════════════════════════════════════════════
# 2. LearningGoalEngine — 自主學習目標產生器
# ═══════════════════════════════════════════════════════════════


class LearningGoalEngine:
    """
    根據：
      - 用戶偏好主題（InteractionProfiler）
      - 任務失敗記錄
      - 知識缺口（最近問了但答得不好的問題）
    自主產生下一輪學習目標清單。
    """

    GOALS_FILE = _DATA_DIR / "learning_goals.json"

    # 預設種子主題（啟動時沒有任何歷史資料時使用）
    _SEED_TOPICS = [
        "Python 非同步程式設計",
        "智能體協作架構",
        "自然語言處理基礎",
        "RAG 檢索增強生成",
        "Flask 後端最佳實踐",
        "用戶互動設計",
        "機器學習模型評估",
    ]

    def __init__(self, profiler: InteractionProfiler):
        self.profiler = profiler
        self.goals: List[Dict] = _load_json(self.GOALS_FILE, [])

    def generate(self, error_log: List[Dict] = None) -> List[Dict]:
        """產生新一批學習目標，去重後寫入檔案。"""
        new_goals = []

        # (a) 基於用戶偏好主題
        for topic in self.profiler.get_top_topics(8):
            new_goals.append(
                {
                    "id": f"topic_{topic[:20]}",
                    "type": "topic_expansion",
                    "query": f"深入了解：{topic}",
                    "priority": 2,
                    "source": "user_preference",
                }
            )

        # (b) 基於任務失敗（如果有錯誤記錄）
        if error_log:
            for err in error_log[-10:]:
                q = err.get("prompt") or err.get("message") or ""
                if q:
                    new_goals.append(
                        {
                            "id": f"error_{hash(q) % 100000}",
                            "type": "failure_recovery",
                            "query": f"如何解決：{q[:80]}",
                            "priority": 1,
                            "source": "error_recovery",
                        }
                    )

        # (c) 種子主題（確保系統有基礎知識）
        existing_ids = {g["id"] for g in self.goals}
        for topic in self._SEED_TOPICS:
            gid = f"seed_{topic[:20]}"
            if gid not in existing_ids:
                new_goals.append(
                    {
                        "id": gid,
                        "type": "seed",
                        "query": topic,
                        "priority": 3,
                        "source": "seed",
                    }
                )

        # 合併去重，按優先級排序
        existing_ids = {g["id"] for g in self.goals}
        for g in new_goals:
            if g["id"] not in existing_ids:
                g["status"] = "pending"
                g["created_at"] = datetime.now().isoformat()
                self.goals.append(g)
                existing_ids.add(g["id"])

        self.goals.sort(key=lambda x: x.get("priority", 9))
        _save_json(self.GOALS_FILE, self.goals)
        pending = [g for g in self.goals if g.get("status") == "pending"]
        logger.info("[GoalEngine] 待學習目標: %d 個", len(pending))
        return pending[:5]  # 每輪最多取前 5 個執行

    def mark_done(self, goal_id: str, result_summary: str = ""):
        for g in self.goals:
            if g["id"] == goal_id:
                g["status"] = "completed"
                g["completed_at"] = datetime.now().isoformat()
                g["result"] = result_summary[:300]
                break
        _save_json(self.GOALS_FILE, self.goals)

    def get_pending_count(self) -> int:
        return sum(1 for g in self.goals if g.get("status") == "pending")


# ═══════════════════════════════════════════════════════════════
# 3. DataSeeker — 主動資料蒐集引擎
# ═══════════════════════════════════════════════════════════════


class DataSeeker:
    """
    主動從多個來源蒐集資料：
      - 本地對話記錄 (conversations.json)
      - 任務歷史 (task_history.json)
      - 學習日誌 (learning_log.json)
      - 外部 API（Together AI / requests）
    每次 seek 回傳結構化的知識片段，供 UnifiedLearningHub 整合。
    """

    SEEK_LOG_FILE = _LOGS_DIR / "data_seeker.log"

    def __init__(self, data_dir: Path = _DATA_DIR):
        self.data_dir = data_dir
        self._session = None  # requests.Session（延遲初始化）

    # ── 主要入口 ──────────────────────────────────────────────

    def seek(self, goal: Dict, together_api_key: str = "") -> Dict:
        """
        針對單一學習目標蒐集資料。
        回傳 {"goal_id", "query", "fragments": [...], "source", "timestamp"}
        """
        query = goal.get("query", "")
        goal_type = goal.get("type", "topic_expansion")
        fragments = []

        # 1. 從本地對話記錄中找相關片段
        fragments += self._seek_conversations(query)

        # 2. 從任務歷史找相關任務
        fragments += self._seek_tasks(query)

        # 3. 從學習日誌找相關知識
        fragments += self._seek_learning_log(query)

        # 4. 從程式碼檔案找相關片段
        fragments += self._seek_code_files(query)

        # 5. 從錯誤日誌提取失敗經驗
        fragments += self._seek_error_logs(query)

        # 6. 從 session 追蹤資料提取
        fragments += self._seek_session_data(query)

        # 7. 如果本地資料不足，優先 Brave 搜尋，次選 Together API
        if len(fragments) < 3:
            brave_key = os.getenv("BRAVE_API_KEY", "")
            if brave_key:
                brave_frags = self._seek_brave(query, brave_key)
                fragments += brave_frags
            elif together_api_key:
                ext = self._seek_external(query, together_api_key)
                if ext:
                    fragments.append(ext)

        result = {
            "goal_id": goal.get("id"),
            "query": query,
            "goal_type": goal_type,
            "fragments": fragments,
            "fragment_count": len(fragments),
            "source": "multi_source",
            "timestamp": datetime.now().isoformat(),
        }
        self._log_seek(query, len(fragments))
        return result

    # ── 來源：本地對話 ────────────────────────────────────────

    def _seek_conversations(self, query: str) -> List[Dict]:
        conv_file = self.data_dir / "conversations.json"
        conversations = _load_json(conv_file, [])
        if not conversations:
            return []

        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower()))
        scored = []
        for conv in conversations:
            text = (
                (conv.get("prompt") or conv.get("user_message") or "")
                + " "
                + (conv.get("response") or "")
            )
            text_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower()))
            overlap = len(q_tokens & text_tokens)
            if overlap >= 1:
                scored.append((overlap, conv))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "type": "conversation",
                "content": (
                    c.get("prompt", "")[:120] + " → " + c.get("response", "")[:200]
                ),
                "score": score,
                "timestamp": c.get("timestamp", ""),
            }
            for score, c in scored[:3]
        ]

    # ── 來源：任務歷史 ────────────────────────────────────────

    def _seek_tasks(self, query: str) -> List[Dict]:
        task_files = [
            self.data_dir / "task_history.json",
            _PROJECT_ROOT / "tasks" / "task_history.json",
        ]
        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower()))
        results = []
        for tf in task_files:
            tasks = _load_json(tf, [])
            for task in tasks:
                title = task.get("title", "")
                desc = task.get("description", "")
                text_tokens = set(
                    re.findall(r"[\w\u4e00-\u9fff]{2,}", (title + " " + desc).lower())
                )
                if q_tokens & text_tokens:
                    results.append(
                        {
                            "type": "task",
                            "content": f"任務: {title} | 狀態: {task.get('status', '?')}",
                            "score": len(q_tokens & text_tokens),
                            "timestamp": task.get("completed_at")
                            or task.get("created_at", ""),
                        }
                    )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:2]

    # ── 來源：學習日誌 ────────────────────────────────────────

    def _seek_learning_log(self, query: str) -> List[Dict]:
        log_file = self.data_dir / "learning_log.json"
        entries = _load_json(log_file, [])
        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower()))
        results = []
        for entry in entries:
            text = (
                entry.get("summary") or entry.get("content") or entry.get("topic") or ""
            )
            text_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower()))
            overlap = len(q_tokens & text_tokens)
            if overlap >= 1:
                results.append(
                    {
                        "type": "learning_log",
                        "content": text[:250],
                        "score": overlap,
                        "timestamp": entry.get("timestamp", ""),
                    }
                )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:2]

    # ── 來源：外部 API ────────────────────────────────────────

    _OFFLINE_UNTIL: Optional[datetime] = None  # 斷線冷卻，類別層級共享

    def _seek_external(self, query: str, together_api_key: str) -> Optional[Dict]:
        """
        向 Together AI 請求外部知識摘要。
        具備以下容錯機制：
          - 連線逾時 15 秒
          - 偵測到網路不通時進入 5 分鐘冷卻（避免重複嘗試堵塞）
          - 429 / 5xx 亦觸發冷卻
          - 完整異常捕捉，不讓外部失敗中斷整個學習週期
        """
        # 冷卻期內直接跳過
        now = datetime.now()
        if DataSeeker._OFFLINE_UNTIL and now < DataSeeker._OFFLINE_UNTIL:
            remaining = (DataSeeker._OFFLINE_UNTIL - now).seconds
            logger.debug("[DataSeeker] 冷卻中，跳過外部 API (%ds)", remaining)
            return None

        if not together_api_key:
            return None

        try:
            import requests as req_mod

            prompt = f"請用繁體中文，簡潔回答以下問題（150字以內）：\n{query}"
            resp = req_mod.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {together_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.3,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                answer = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if answer:
                    DataSeeker._OFFLINE_UNTIL = None  # 成功，清除冷卻
                    return {
                        "type": "external_api",
                        "content": answer,
                        "score": 5,
                        "timestamp": datetime.now().isoformat(),
                    }
            elif resp.status_code in (429, 500, 502, 503, 504):
                # 流量限制或伺服器錯誤 → 冷卻 5 分鐘
                DataSeeker._OFFLINE_UNTIL = now + timedelta(minutes=5)
                logger.warning(
                    "[DataSeeker] Together API 回傳 %d，冷卻 5 分鐘", resp.status_code
                )
        except OSError as e:
            # 網路不通（Connection refused / No route to host）
            DataSeeker._OFFLINE_UNTIL = now + timedelta(minutes=5)
            logger.warning("[DataSeeker] 網路中斷，冷卻 5 分鐘: %s", e)
        except Exception as e:
            logger.debug("[DataSeeker] 外部 API 失敗: %s", e)
        return None

    # ── 來源：Brave Search API ────────────────────────────────

    def _seek_brave(self, query: str, api_key: str) -> List[Dict]:
        """使用 Brave Search API 搜尋網路資料。"""
        now = datetime.now()
        if DataSeeker._OFFLINE_UNTIL and now < DataSeeker._OFFLINE_UNTIL:
            return []
        try:
            import requests as req_mod

            resp = req_mod.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                params={"q": query, "count": 5, "text_decorations": False},
                timeout=12,
            )
            if resp.status_code == 200:
                results = resp.json().get("web", {}).get("results", [])
                DataSeeker._OFFLINE_UNTIL = None
                fragments = []
                for r in results[:5]:
                    content = r.get("description") or r.get("extra_snippets", [""])[0]
                    if content and len(content) > 30:
                        fragments.append(
                            {
                                "type": "brave_search",
                                "content": f"[{r.get('title', '')}] {content}",
                                "url": r.get("url", ""),
                                "score": 6,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                logger.info(
                    "[DataSeeker] Brave 搜尋「%s」→ %d 筆", query[:30], len(fragments)
                )
                return fragments
            elif resp.status_code in (429, 500, 502, 503, 504):
                DataSeeker._OFFLINE_UNTIL = now + timedelta(minutes=5)
                logger.warning("[DataSeeker] Brave API 回傳 %d", resp.status_code)
        except Exception as e:
            DataSeeker._OFFLINE_UNTIL = now + timedelta(minutes=5)
            logger.debug("[DataSeeker] Brave 搜尋失敗: %s", e)
        return []

    # ── 來源：程式碼分析 ──────────────────────────────────────

    def _seek_code_files(self, query: str) -> List[Dict]:
        """掃描專案 .py 檔案，找出與查詢相關的程式碼片段。"""
        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower()))
        results = []
        project_root = _PROJECT_ROOT
        py_files = list(project_root.rglob("*.py"))[:60]  # 最多掃 60 個檔案
        for pyf in py_files:
            if "__pycache__" in str(pyf):
                continue
            try:
                text = pyf.read_text(encoding="utf-8", errors="ignore")[:3000]
                text_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower()))
                overlap = len(q_tokens & text_tokens)
                if overlap >= 2:
                    # 找最相關的前 3 行
                    relevant_lines = [
                        ln
                        for ln in text.splitlines()
                        if any(t in ln.lower() for t in q_tokens)
                    ][:3]
                    results.append(
                        {
                            "type": "code_file",
                            "content": f"{pyf.name}: "
                            + " | ".join(relevant_lines)[:200],
                            "score": overlap,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
            except Exception:
                pass
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:2]

    # ── 來源：錯誤日誌 ────────────────────────────────────────

    def _seek_error_logs(self, query: str) -> List[Dict]:
        """從錯誤日誌中提取相關失敗經驗。"""
        error_files = [
            self.data_dir / "error_log.json",
            _PROJECT_ROOT / "logs" / "error_log.json",
        ]
        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower()))
        results = []
        for ef in error_files:
            entries = _load_json(ef, [])
            for e in entries[-100:]:  # 只看最近 100 筆
                text = " ".join(
                    [
                        str(e.get("error_message", "")),
                        str(e.get("prompt", "")),
                        str(e.get("error_type", "")),
                    ]
                )
                text_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower()))
                overlap = len(q_tokens & text_tokens)
                if overlap >= 1:
                    results.append(
                        {
                            "type": "error_log",
                            "content": f"[{e.get('error_type', '')}] {text[:200]}",
                            "score": overlap,
                            "timestamp": e.get("timestamp", ""),
                        }
                    )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:2]

    # ── 來源：Session 追蹤 ────────────────────────────────────

    def _seek_session_data(self, query: str) -> List[Dict]:
        """從 session_tracking.json 提取相關 session 資料。"""
        sf = self.data_dir / "session_tracking.json"
        raw = _load_json(sf, [])
        # 支援 list 或 dict 格式
        if isinstance(raw, dict):
            sessions = list(raw.values())
        elif isinstance(raw, list):
            sessions = raw
        else:
            return []
        if not sessions:
            return []
        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower()))
        results = []
        for s in sessions[-50:]:
            text = " ".join(
                [
                    str(s.get("summary", "")),
                    str(s.get("topics", "")),
                    str(s.get("feedback", "")),
                ]
            )
            text_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower()))
            overlap = len(q_tokens & text_tokens)
            if overlap >= 1:
                results.append(
                    {
                        "type": "session",
                        "content": text[:200],
                        "score": overlap,
                        "timestamp": s.get("timestamp", ""),
                    }
                )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:2]

    # ── 日誌 ──────────────────────────────────────────────────

    def _log_seek(self, query: str, fragment_count: int):
        try:
            self.SEEK_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.SEEK_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                    f"query={query[:60]!r} fragments={fragment_count}\n"
                )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# 4. KnowledgeIntegrator — 將 DataSeeker 結果寫入學習中樞
# ═══════════════════════════════════════════════════════════════


class KnowledgeIntegrator:
    """
    將 DataSeeker 的搜尋結果整合進本地知識庫。
    目前寫入 learning_log.json，未來可擴充至向量資料庫。
    """

    KNOWLEDGE_FILE = _DATA_DIR / "orchestrated_knowledge.json"

    def __init__(self):
        self.records: List[Dict] = _load_json(self.KNOWLEDGE_FILE, [])

    def integrate(self, seek_result: Dict):
        if not seek_result.get("fragments"):
            return
        record = {
            "goal_id": seek_result.get("goal_id"),
            "query": seek_result.get("query"),
            "goal_type": seek_result.get("goal_type"),
            "fragments": seek_result.get("fragments", []),
            "integrated_at": datetime.now().isoformat(),
        }
        self.records.append(record)
        # 只保留最近 500 筆
        if len(self.records) > 500:
            self.records = self.records[-500:]
        _save_json(self.KNOWLEDGE_FILE, self.records)
        logger.info(
            "[KnowledgeIntegrator] 整合完成: %s (%d 片段)",
            seek_result.get("query", "")[:50],
            len(seek_result.get("fragments", [])),
        )

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """簡單關鍵字搜尋已整合的知識。"""
        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower()))
        scored = []
        for rec in self.records:
            text = rec.get("query", "") + " ".join(
                f.get("content", "") for f in rec.get("fragments", [])
            )
            text_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower()))
            overlap = len(q_tokens & text_tokens)
            if overlap:
                scored.append((overlap, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]


# ═══════════════════════════════════════════════════════════════
# 5. AutonomousLearningOrchestrator — 主協調器
# ═══════════════════════════════════════════════════════════════


class AutonomousLearningOrchestrator:
    """
    自主學習協調器主類。

    協調器迴圈邏輯（每 interval 秒執行一次）：
      1. 載入最新對話/任務資料
      2. InteractionProfiler 更新用戶偏好
      3. LearningGoalEngine 產生學習目標
      4. DataSeeker 針對每個目標蒐集資料
      5. KnowledgeIntegrator 整合資料
      6. 將學習摘要寫入狀態檔，供 Flask API 查詢
      7. 睡眠 interval 秒後重複

    Usage:
        orchestrator = AutonomousLearningOrchestrator(
            together_api_key="...",   # 可選，有則啟用外部 API
            interval=600,             # 每 10 分鐘執行一輪
        )
        orchestrator.start()
        # ... Flask 伺服器運行中 ...
        orchestrator.stop()
    """

    STATUS_FILE = _DATA_DIR / "orchestrator_status.json"

    def __init__(
        self,
        together_api_key: str = "",
        interval: int = 600,  # 預設每 10 分鐘一輪
        data_dir: Path = _DATA_DIR,
    ):
        self.together_api_key = together_api_key
        self.interval = max(60, interval)  # 最少 60 秒
        self.data_dir = data_dir

        # 核心學習子模組
        self.profiler = InteractionProfiler()
        self.goal_engine = LearningGoalEngine(self.profiler)
        self.seeker = DataSeeker(data_dir)
        self.integrator = KnowledgeIntegrator()

        # 蒸餾 + 驗證（KAL Loop 新增節點）
        self.distiller = _try_import_distiller()
        self.validator = _try_import_validator()

        # 智能體通訊匯流排
        (self._broker, self._registry, self._EventType, self._Message) = (
            _try_import_comms()
        )
        if self._registry:
            self._registry.register(
                "orchestrator",
                "learning",
                ["knowledge_acquisition", "distillation", "validation"],
            )

        # 新增：標籤引擎
        try:
            from tag_engine import TagEngine

            self.tag_engine: Optional[Any] = TagEngine()
            logger.info("[Orchestrator] TagEngine 已載入")
        except ImportError as e:
            self.tag_engine = None
            logger.warning("[Orchestrator] TagEngine 未載入: %s", e)

        # 新增：智能體協作中心
        try:
            from agent_collaboration_hub import AgentCollaborationHub

            self.collab_hub: Optional[Any] = AgentCollaborationHub()
            logger.info("[Orchestrator] AgentCollaborationHub 已載入")
        except ImportError as e:
            self.collab_hub = None
            logger.warning("[Orchestrator] AgentCollaborationHub 未載入: %s", e)

        # 執行狀態
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cycle_count = 0
        self._last_cycle_at: Optional[str] = None
        self._lock = threading.Lock()

        logger.info("[Orchestrator] 已初始化 (interval=%ds)", self.interval)

    # ── 生命週期 ──────────────────────────────────────────────

    def start(self):
        """啟動協調器背景執行緒（daemon，不阻塞主程序）。"""
        with self._lock:
            if self._running:
                logger.warning("[Orchestrator] 已在執行中，略過重複啟動")
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._loop,
                name="autonomous-learning-orchestrator",
                daemon=True,
            )
            self._thread.start()
        logger.info("[Orchestrator] 背景學習迴圈已啟動")

    def stop(self):
        """停止協調器。"""
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("[Orchestrator] 已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 主迴圈 ────────────────────────────────────────────────

    def _loop(self):
        logger.info("[Orchestrator] 迴圈開始，首輪延遲 30 秒等待伺服器穩定...")
        time.sleep(30)  # 等待 Flask 完全啟動

        while self._running:
            try:
                self._run_cycle()
            except Exception as e:
                logger.error("[Orchestrator] 迴圈異常: %s", e, exc_info=True)
            # 等待下一輪（每隔 10 秒檢查一次 _running 狀態）
            elapsed = 0
            while elapsed < self.interval and self._running:
                time.sleep(min(10, self.interval - elapsed))
                elapsed += 10

    def _run_cycle(self):
        """執行一輪完整的學習協調週期。"""
        cycle_start = datetime.now()
        logger.info("[Orchestrator] ── 第 %d 輪學習週期開始 ──", self._cycle_count + 1)

        # 生命週期追蹤：建立本輪 KAL 訊息封裝
        _cycle_env = None
        if self.collab_hub:
            try:
                _cycle_env = self.collab_hub.submit_message(
                    payload=f"KAL 第 {self._cycle_count + 1} 輪自主學習週期",
                    sender="orchestrator",
                    recipient="learner",
                    context_id=f"kal_cycle_{self._cycle_count + 1}",
                )
                self.collab_hub.start_message(_cycle_env.message_id, "learner")
            except Exception as _e:
                logger.debug("[Orchestrator] 生命週期掛鉤失敗（不影響迴圈）: %s", _e)
                _cycle_env = None

        # ① 載入最新資料
        conversations = _load_json(self.data_dir / "conversations.json", [])
        task_history = _load_json(self.data_dir / "task_history.json", [])
        tasks_file = _PROJECT_ROOT / "tasks" / "task_history.json"
        if tasks_file.exists():
            task_history += _load_json(tasks_file, [])
        error_log = _load_json(self.data_dir / "error_log.json", [])

        # ② 更新互動偏好檔案
        profile = self.profiler.update(conversations, task_history)
        top_topics = self.profiler.get_top_topics(5)
        style_hint = self.profiler.get_style_hint()

        # ③ 產生學習目標
        goals = self.goal_engine.generate(error_log=error_log)

        # ③.5 標籤引擎：批次標記最新對話和任務
        tag_stats: Dict = {}
        if self.tag_engine:
            try:
                new_conv_count = self.tag_engine.bulk_tag_conversations(
                    conversations[-50:]  # 只標記最近 50 筆，避免耗時過長
                )
                new_task_count = self.tag_engine.bulk_tag_tasks(task_history[-30:])
                for goal in goals:
                    self.tag_engine.tag_goal(goal)
                self.tag_engine.flush()
                tag_stats = self.tag_engine.tag_stats()
                logger.info(
                    "[TagEngine] 已標記 %d 對話 / %d 任務 | 標籤庫: %d 個",
                    new_conv_count,
                    new_task_count,
                    tag_stats.get("total_tags", 0),
                )
            except Exception as te:
                logger.warning("[TagEngine] 標記失敗: %s", te)

        # ④ KAL Loop：搜尋 → 蒸餾 → 驗證 → (不夠→再學) → 整合
        integrated = 0
        retry_goals: List[Dict] = []  # 需要再學的目標

        MAX_ROUNDS = 3  # 每個目標最多重試 3 輪

        for goal in goals:
            goal_query = goal.get("query", "")
            passed_wikis: List[Dict] = []
            sources_used: int = 0
            rounds: int = 0

            while rounds < MAX_ROUNDS:
                rounds += 1
                seek_result = self.seeker.seek(goal, self.together_api_key)
                fragments = seek_result.get("fragments", [])
                sources_used += seek_result.get("fragment_count", 0)

                if not fragments:
                    logger.debug(
                        "[KAL] 目標 '%s' 第%d輪無資料", goal_query[:30], rounds
                    )
                    break

                # 蒸餾
                if self.distiller:
                    wikis = self.distiller.distill_batch(fragments)
                else:
                    wikis = [
                        {
                            "topic": goal_query[:20],
                            "summary": f.get("content", ""),
                            "key_facts": [],
                            "confidence": 0.6,
                            "source_type": f.get("type", "unknown"),
                            "distilled_at": datetime.now().isoformat(),
                        }
                        for f in fragments
                    ]

                # 驗證
                if self.validator and wikis:
                    batch_result = self.validator.validate_batch(wikis)
                    passed_wikis.extend(batch_result["passed"])
                    retry_needed = len(batch_result["retry"]) > 0
                else:
                    passed_wikis.extend(wikis)
                    retry_needed = False

                if passed_wikis and not retry_needed:
                    logger.info(
                        "[KAL] Converged ✓ | %d rounds | %d sources | %s",
                        rounds,
                        sources_used,
                        goal_query[:30],
                    )
                    break
                elif rounds < MAX_ROUNDS:
                    logger.info(
                        "[KAL] 不夠→再學 (round=%d) | %s", rounds, goal_query[:30]
                    )
                else:
                    logger.info(
                        "[KAL] 達到最大輪次 (%d) | %s", MAX_ROUNDS, goal_query[:30]
                    )

            # 整合通過的知識
            if passed_wikis:
                # 把 wiki 注入 seek_result 供 integrator 使用
                seek_result["wikis"] = passed_wikis
                seek_result["rounds"] = rounds
                seek_result["sources_used"] = sources_used
                self.integrator.integrate(seek_result)

                if self.tag_engine:
                    try:
                        ktags = self.tag_engine.tag_knowledge(
                            seek_result, knowledge_id=goal["id"]
                        )
                        seek_result["tags"] = ktags
                    except Exception:
                        pass
                if self.collab_hub:
                    try:
                        self.collab_hub.share_knowledge(
                            agent="data_seeker",
                            topic=goal_query,
                            content=" | ".join(
                                w.get("summary", "")[:150] for w in passed_wikis[:3]
                            ),
                            tags=seek_result.get("tags", []),
                            confidence=sum(
                                w.get("confidence", 0.5) for w in passed_wikis
                            )
                            / max(len(passed_wikis), 1),
                        )
                    except Exception:
                        pass
                self.goal_engine.mark_done(
                    goal["id"],
                    result_summary=f"通過 {len(passed_wikis)} 篇 wiki（{rounds} 輪）",
                )
                integrated += 1

                # 發佈學習事件到 message broker
                if self._broker and self._EventType and self._Message:
                    try:
                        self._broker.publish(
                            self._Message(
                                sender="orchestrator",
                                receiver="all",
                                event_type=self._EventType.LEARNING_UPDATED,
                                data={
                                    "topic": goal_query,
                                    "wikis_count": len(passed_wikis),
                                    "rounds": rounds,
                                    "sources": sources_used,
                                },
                                priority=5,
                            )
                        )
                    except Exception:
                        pass
            else:
                logger.debug("[KAL] 目標 '%s' 未通過驗證，略過", goal_query[:30])

        # ⑤ 協作中心：發佈本輪學習摘要 + 委派標籤任務
        collab_report: Dict = {}
        if self.collab_hub:
            try:
                # 讓 learner 智能體把學習洞察貢獻進共享庫
                self.collab_hub.auto_share_orchestrator_insights(
                    {
                        "top_topics": top_topics,
                        "style_hint": style_hint,
                    }
                )
                # 如果有大量未標記資料，委派給 tagger 智能體
                if len(conversations) > 100 and self.tag_engine:
                    self.collab_hub.delegate_task(
                        title="批次標記舊對話",
                        content=f"需標記 {len(conversations)} 筆對話記錄",
                        required_capabilities=["tagging"],
                        required_tags=["domain/system"],
                        priority=3,
                        source_agent="orchestrator",
                    )
                # 更新各智能體心跳
                for agent_name in [
                    "learner",
                    "data_seeker",
                    "tagger",
                    "interaction_profiler",
                ]:
                    self.collab_hub.heartbeat(agent_name, "idle")
                collab_report = {
                    "agents": len(self.collab_hub.agent_list()),
                    "pending_tasks": len(self.collab_hub.pending_tasks()),
                }
                self.collab_hub.flush()
            except Exception as ce:
                logger.warning("[CollabHub] 協作中心更新失敗: %s", ce)

        # ⑥ 更新狀態檔（供 Flask /api/orchestrator/status 查詢）
        self._cycle_count += 1
        self._last_cycle_at = cycle_start.isoformat()
        duration = (datetime.now() - cycle_start).total_seconds()

        status = {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "last_cycle_at": self._last_cycle_at,
            "last_cycle_duration_sec": round(duration, 1),
            "goals_processed": len(goals),
            "goals_integrated": integrated,
            "pending_goals": self.goal_engine.get_pending_count(),
            "top_topics": top_topics,
            "style_hint": style_hint,
            "interval_sec": self.interval,
            "tag_stats": tag_stats,
            "collaboration": collab_report,
            "kal_loop": {
                "distiller_active": self.distiller is not None,
                "validator_active": self.validator is not None,
                "brave_api": bool(os.getenv("BRAVE_API_KEY")),
                "max_rounds_per_goal": 3,
            },
        }
        _save_json(self.STATUS_FILE, status)

        logger.info(
            "[Orchestrator] 第 %d 輪完成 (%.1fs) | 目標: %d/%d 整合 | 主題: %s",
            self._cycle_count,
            duration,
            integrated,
            len(goals),
            top_topics[:3],
        )

        # 生命週期追蹤：標記本輪完成
        if self.collab_hub and _cycle_env:
            try:
                self.collab_hub.resolve_message(
                    _cycle_env.message_id,
                    result=(
                        f"週期 {self._cycle_count} 完成 | "
                        f"整合 {integrated}/{len(goals)} 目標 | "
                        f"主題: {', '.join(top_topics[:3])}"
                    ),
                    model_used="kal_orchestrator",
                    agent="learner",
                )
            except Exception as _e:
                logger.debug("[Orchestrator] 生命週期 resolve 失敗: %s", _e)

    # ── 外部介面 ──────────────────────────────────────────────

    def get_status(self) -> Dict:
        """回傳目前執行狀態（供 Flask API 使用）。"""
        stored = _load_json(self.STATUS_FILE, {})
        stored["running"] = self._running
        stored["cycle_count"] = self._cycle_count
        return stored

    def inject_user_feedback(self, message: str, rating: int = 0):
        """
        接收用戶即時回饋，立即觸發一輪快速學習。
        rating: 1=正面, -1=負面, 0=中性
        """
        logger.info("[Orchestrator] 收到用戶回饋 (rating=%d): %s", rating, message[:60])
        if rating < 0:
            # 負面回饋 → 記錄為高優先錯誤目標
            self.goal_engine.goals.insert(
                0,
                {
                    "id": f"feedback_{int(time.time())}",
                    "type": "failure_recovery",
                    "query": f"改善回應：{message[:80]}",
                    "priority": 1,
                    "status": "pending",
                    "source": "user_feedback",
                    "created_at": datetime.now().isoformat(),
                },
            )
            _save_json(self.goal_engine.GOALS_FILE, self.goal_engine.goals)

    def submit_data_for_learning(
        self, data: str, source: str = "user", context_id: str = None
    ) -> Dict:
        """
        手動提交資料進入學習流程（帶完整生命週期追蹤）。
        回傳 dict：message_id、knowledge_id、signals、status。
        """
        if not self.collab_hub:
            return {"error": "collab_hub 未啟用", "status": "failed"}

        env = self.collab_hub.submit_message(
            payload=data,
            sender=source,
            recipient="learner",
            context_id=context_id,
        )
        self.collab_hub.start_message(env.message_id, "learner")

        try:
            # 訊號萃取（內嵌實作，避免跨目錄 import）
            _zh = re.findall(r"[\u4e00-\u9fff]{2,10}", data)
            _en = [t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", data)]
            _stop_zh = {
                "這個",
                "那個",
                "目前",
                "現在",
                "需要",
                "可以",
                "幫我",
                "然後",
                "如果",
                "但是",
            }
            _stop_en = {
                "this",
                "that",
                "with",
                "from",
                "have",
                "will",
                "would",
                "should",
            }
            from collections import Counter as _Counter

            _cnt: Dict[str, int] = _Counter(
                [w for w in _zh if w not in _stop_zh]
                + [w for w in _en if w not in _stop_en]
            )
            signals = [w for w, _ in _cnt.most_common(20)]

            # 貢獻至共享知識庫
            tags = signals[:5] + [f"source/{source}", "type/manual_input"]
            kid = self.collab_hub.share_knowledge(
                agent="learner",
                topic=f"手動資料：{data[:40].strip()}",
                content=data[:1000],
                tags=tags,
                confidence=0.75,
            )

            # 更新互動分析（把資料當作一筆對話紀錄）
            self.profiler.update([{"role": "user", "content": data}], [])

            self.collab_hub.resolve_message(
                env.message_id,
                result=f"萃取 {len(signals)} 個訊號，知識 ID: {kid}",
                model_used="signal_extractor",
                agent="learner",
            )
            logger.info(
                "[Orchestrator] submit_data_for_learning 完成 | signals=%d kid=%s",
                len(signals),
                kid,
            )
            return {
                "message_id": env.message_id,
                "knowledge_id": kid,
                "signals": signals,
                "status": "completed",
            }

        except Exception as exc:
            self.collab_hub.fail_message(
                env.message_id, str(exc), "extraction_error", "learner"
            )
            logger.warning("[Orchestrator] submit_data_for_learning 失敗: %s", exc)
            return {"message_id": env.message_id, "error": str(exc), "status": "failed"}

    def search_knowledge(self, query: str) -> List[Dict]:
        """讓 Flask 路由可以直接搜尋已整合的知識。"""
        return self.integrator.search(query)


# ═══════════════════════════════════════════════════════════════
# 模組級單例（供 Flask 伺服器 import 使用）
# ═══════════════════════════════════════════════════════════════

_orchestrator_instance: Optional[AutonomousLearningOrchestrator] = None


def get_orchestrator(
    together_api_key: str = "",
    interval: int = 600,
) -> AutonomousLearningOrchestrator:
    """
    取得（或建立）全域單例協調器。
    在 Flask 伺服器啟動時呼叫一次即可。
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = AutonomousLearningOrchestrator(
            together_api_key=together_api_key,
            interval=interval,
        )
    return _orchestrator_instance
