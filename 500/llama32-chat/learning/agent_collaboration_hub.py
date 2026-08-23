#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體協作中心 (Agent Collaboration Hub)
讓各智能體能夠：
  1. 互相委派任務（Task Delegation）
  2. 分享學習結果（Knowledge Sharing）
  3. 能力匹配（Capability Matching）
  4. 集體記憶（Collective Memory）
  5. 協作歷史追蹤（Collaboration Audit）

與現有 MessageBroker / AgentRegistry 的關係：
  - 本模組作為「上層語義層」，使用 JSON 檔案持久化
  - 不依賴現有 MessageBroker（避免循環依賴），獨立運作
  - 可透過 TagEngine 讓任務帶標籤，實現精準分派
"""

import json
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT = _THIS_DIR.parent
_DATA_DIR = _PROJECT / "data"
_COLLAB_DIR = _DATA_DIR / "collaboration"


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
# 0. MessageEnvelope / MessageLifecycle / AgentResponse
#    訊息生命週期：進來 → 處理中 → 完成 / 失敗（含 retry）
# ═══════════════════════════════════════════════════════════════


class MessageEnvelope:
    """每條訊息的完整元資料封裝（誰發、發給誰、何時、哪個 context）。"""

    def __init__(
        self,
        payload: str,
        sender: str = "user",
        recipient: str = "dispatcher",
        context_id: str = None,
    ):
        self.message_id = f"msg_{uuid.uuid4().hex[:12]}"
        self.created_at = time.time()
        self.sender = sender
        self.recipient = recipient
        self.payload = payload
        self.context_id = context_id or f"ctx_{int(self.created_at)}"

    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "sender": self.sender,
            "recipient": self.recipient,
            "payload": (self.payload or "")[:500],
            "context_id": self.context_id,
        }


class MessageLifecycle:
    """
    追蹤一條訊息從進入到完成的完整狀態。
    狀態流：queued → processing → completed / failed → (retry → queued)
    """

    MAX_RETRIES = 3

    def __init__(self, envelope: MessageEnvelope):
        self.message_id = envelope.message_id
        self.context_id = envelope.context_id
        self.status = "queued"
        self.current_agent = envelope.recipient
        self.queued_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.duration_ms: Optional[int] = None
        self.retry_count = 0
        self.error: Optional[str] = None
        self.error_type: Optional[str] = None
        self.response: Optional["AgentResponse"] = None

    def start(self, agent: str):
        self.status = "processing"
        self.current_agent = agent
        self.started_at = time.time()

    def complete(self, response: "AgentResponse"):
        self.status = "completed"
        self.finished_at = time.time()
        self.duration_ms = int(
            (self.finished_at - (self.started_at or self.queued_at)) * 1000
        )
        self.response = response
        self.error = None
        self.error_type = None

    def fail(self, error: str, error_type: str = "unknown"):
        self.status = "failed"
        self.finished_at = time.time()
        self.duration_ms = int(
            (self.finished_at - (self.started_at or self.queued_at)) * 1000
        )
        self.error = error
        self.error_type = error_type
        self.retry_count += 1

    @property
    def can_retry(self) -> bool:
        return self.status == "failed" and self.retry_count < self.MAX_RETRIES

    def reset_for_retry(self, new_agent: str = None):
        if not self.can_retry:
            raise RuntimeError(
                f"訊息 {self.message_id} 已達最大重試次數 {self.MAX_RETRIES}"
            )
        self.status = "queued"
        self.started_at = None
        self.finished_at = None
        self.duration_ms = None
        if new_agent:
            self.current_agent = new_agent

    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "context_id": self.context_id,
            "status": self.status,
            "current_agent": self.current_agent,
            "queued_at": datetime.fromtimestamp(self.queued_at).isoformat(),
            "started_at": datetime.fromtimestamp(self.started_at).isoformat()
            if self.started_at
            else None,
            "finished_at": datetime.fromtimestamp(self.finished_at).isoformat()
            if self.finished_at
            else None,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "error": self.error,
            "error_type": self.error_type,
            "response": self.response.to_dict() if self.response else None,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "MessageLifecycle":
        env = MessageEnvelope.__new__(MessageEnvelope)
        env.message_id = d["message_id"]
        env.created_at = time.time()
        env.sender = "restored"
        env.recipient = d.get("current_agent", "dispatcher")
        env.payload = ""
        env.context_id = d.get("context_id", "")
        lc = cls(env)
        lc.status = d.get("status", "queued")
        lc.current_agent = d.get("current_agent", "dispatcher")
        lc.duration_ms = d.get("duration_ms")
        lc.retry_count = d.get("retry_count", 0)
        lc.error = d.get("error")
        lc.error_type = d.get("error_type")
        if d.get("response"):
            lc.response = AgentResponse.from_dict(d["response"])
        return lc


class AgentResponse:
    """智能體的標準化回應格式（結果 + 模型 + 錯誤）。"""

    def __init__(
        self,
        message_id: str,
        result: str,
        model_used: str = "unknown",
        agent: str = "unknown",
    ):
        self.message_id = message_id
        self.result = result
        self.model_used = model_used
        self.agent = agent
        self.responded_at = time.time()
        self.error: Optional[str] = None
        self.error_type: Optional[str] = None

    @classmethod
    def error_response(
        cls,
        message_id: str,
        error: str,
        error_type: str = "unknown",
        agent: str = "unknown",
    ) -> "AgentResponse":
        r = cls(message_id, "", "none", agent)
        r.error = error
        r.error_type = error_type
        return r

    @classmethod
    def from_dict(cls, d: Dict) -> "AgentResponse":
        r = cls(
            d.get("message_id", ""),
            d.get("result", ""),
            d.get("model_used", "unknown"),
            d.get("agent", "unknown"),
        )
        r.error = d.get("error")
        r.error_type = d.get("error_type")
        return r

    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "result": (self.result or "")[:2000],
            "model_used": self.model_used,
            "agent": self.agent,
            "responded_at": datetime.fromtimestamp(self.responded_at).isoformat(),
            "error": self.error,
            "error_type": self.error_type,
        }


# ═══════════════════════════════════════════════════════════════
# 1. AgentProfile — 單一智能體的能力 + 狀態描述
# ═══════════════════════════════════════════════════════════════


class AgentProfile:
    """描述一個智能體的身份、能力與目前狀態。"""

    def __init__(
        self,
        name: str,
        capabilities: List[str],
        description: str = "",
        tags: List[str] = None,
    ):
        self.name = name
        self.capabilities = set(capabilities)
        self.description = description
        self.tags = set(tags or [])
        self.registered_at = datetime.now().isoformat()
        self.last_active = datetime.now().isoformat()
        self.task_count = 0
        self.success_count = 0
        self.status = "idle"  # idle | busy | offline

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "capabilities": list(self.capabilities),
            "description": self.description,
            "tags": list(self.tags),
            "registered_at": self.registered_at,
            "last_active": self.last_active,
            "task_count": self.task_count,
            "success_count": self.success_count,
            "status": self.status,
            "success_rate": round(self.success_count / max(self.task_count, 1), 3),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "AgentProfile":
        p = cls(
            d["name"],
            d.get("capabilities", []),
            d.get("description", ""),
            d.get("tags", []),
        )
        p.registered_at = d.get("registered_at", p.registered_at)
        p.last_active = d.get("last_active", p.last_active)
        p.task_count = d.get("task_count", 0)
        p.success_count = d.get("success_count", 0)
        p.status = d.get("status", "idle")
        return p


# ═══════════════════════════════════════════════════════════════
# 2. CollaborativeTask — 跨智能體的協作任務
# ═══════════════════════════════════════════════════════════════


class CollaborativeTask:
    """
    一個可在多個智能體間流轉的協作任務。
    lifecycle: created → assigned → in_progress → completed / failed → (可 retry)
    """

    def __init__(
        self,
        title: str,
        content: str,
        required_capabilities: List[str] = None,
        required_tags: List[str] = None,
        priority: int = 2,
        source_agent: str = "orchestrator",
    ):
        self.id = f"ctask_{int(time.time() * 1000)}"
        self.title = title
        self.content = content
        self.required_capabilities = required_capabilities or []
        self.required_tags = required_tags or []
        self.priority = priority  # 1=高 2=中 3=低
        self.source_agent = source_agent
        self.assigned_agent = None
        self.status = "created"
        self.result = None
        self.created_at = datetime.now().isoformat()
        self.assigned_at = None
        self.completed_at = None
        self.retry_count = 0

    def assign(self, agent_name: str):
        self.assigned_agent = agent_name
        self.status = "assigned"
        self.assigned_at = datetime.now().isoformat()

    def complete(self, result: str = ""):
        self.status = "completed"
        self.result = result
        self.completed_at = datetime.now().isoformat()

    def fail(self, reason: str = ""):
        self.status = "failed"
        self.result = reason
        self.completed_at = datetime.now().isoformat()
        self.retry_count += 1

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "required_capabilities": self.required_capabilities,
            "required_tags": self.required_tags,
            "priority": self.priority,
            "source_agent": self.source_agent,
            "assigned_agent": self.assigned_agent,
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at,
            "assigned_at": self.assigned_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
        }


# ═══════════════════════════════════════════════════════════════
# 3. SharedKnowledgeBase — 智能體共享知識庫
# ═══════════════════════════════════════════════════════════════


class SharedKnowledgeBase:
    """
    智能體之間共享的知識倉庫。
    任何智能體學到的知識都可以貢獻進來，其他智能體可以查詢。
    """

    FILE = _COLLAB_DIR / "shared_knowledge.json"
    MAX_RECORDS = 2000

    def __init__(self):
        stored = _load(self.FILE, {})
        self._records: List[Dict] = stored.get("records", [])
        self._contributor_stats: Dict[str, int] = stored.get("contributor_stats", {})

    def contribute(
        self,
        agent: str,
        topic: str,
        content: str,
        tags: List[str] = None,
        confidence: float = 0.8,
    ) -> str:
        """智能體貢獻知識，回傳知識 ID。"""
        kid = f"k_{agent}_{int(time.time() * 1000)}"
        record = {
            "id": kid,
            "agent": agent,
            "topic": topic,
            "content": content[:1000],
            "tags": tags or [],
            "confidence": confidence,
            "contributed_at": datetime.now().isoformat(),
            "access_count": 0,
        }
        self._records.append(record)
        self._contributor_stats[agent] = self._contributor_stats.get(agent, 0) + 1

        # 只保留最新 MAX_RECORDS 筆
        if len(self._records) > self.MAX_RECORDS:
            self._records = self._records[-self.MAX_RECORDS :]
        return kid

    def query(
        self,
        query_text: str = "",
        tags: List[str] = None,
        top_k: int = 5,
        min_confidence: float = 0.0,
    ) -> List[Dict]:
        """查詢共享知識庫。"""
        q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (query_text or "").lower()))
        tag_set = set(tags or [])
        scored: List[Tuple[float, Dict]] = []

        for rec in self._records:
            if rec.get("confidence", 0) < min_confidence:
                continue
            # 標籤匹配分
            rec_tags = set(rec.get("tags", []))
            tag_score = len(rec_tags & tag_set) * 3 if tag_set else 0
            # 文字相似分
            text = (rec.get("topic", "") + " " + rec.get("content", "")).lower()
            text_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text))
            text_score = len(q_tokens & text_tokens) if q_tokens else 0
            total = tag_score + text_score
            if total > 0:
                scored.append((total, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:top_k]]
        # 更新訪問計數（不存檔，下次 flush 時才寫入）
        for r in results:
            r["access_count"] = r.get("access_count", 0) + 1
        return results

    def contributor_stats(self) -> Dict[str, int]:
        return dict(
            sorted(self._contributor_stats.items(), key=lambda x: x[1], reverse=True)
        )

    def flush(self):
        _save(
            self.FILE,
            {
                "records": self._records,
                "contributor_stats": self._contributor_stats,
                "updated_at": datetime.now().isoformat(),
            },
        )


# ═══════════════════════════════════════════════════════════════
# 4. AgentCollaborationHub — 協作中心主類
# ═══════════════════════════════════════════════════════════════


class AgentCollaborationHub:
    """
    智能體協作中心。

    功能：
      - register_agent()     : 登記一個智能體（含能力標籤）
      - delegate_task()      : 建立任務並自動分派給最合適的智能體
      - complete_task()      : 標記任務完成，回報結果
      - share_knowledge()    : 貢獻知識到共享庫
      - query_knowledge()    : 跨智能體查詢知識
      - collaboration_report(): 產出協作現況報告
    """

    AGENTS_FILE = _COLLAB_DIR / "agents.json"
    TASKS_FILE = _COLLAB_DIR / "tasks.json"
    AUDIT_FILE = _COLLAB_DIR / "audit_log.json"
    MESSAGES_FILE = _COLLAB_DIR / "messages.json"
    DLQ_FILE = _COLLAB_DIR / "dead_letter_queue.json"

    PROCESSING_TIMEOUT_SEC = 120  # 訊息在 processing 超過此秒數視為 timeout
    WATCHDOG_INTERVAL_SEC = 30  # watchdog 掃描間隔

    # 預登記的核心智能體（啟動時自動初始化）
    _BUILTIN_AGENTS = [
        {
            "name": "central_nervous",
            "capabilities": [
                "model_selection",
                "health_monitoring",
                "decision_making",
                "coordination",
                "learning",
            ],
            "description": "中樞神經 — 協調所有智能體，負責模型選擇與健康監控",
            "tags": ["domain/orchestrator", "domain/ai", "priority/high"],
        },
        {
            "name": "learner",
            "capabilities": [
                "learning",
                "knowledge_extraction",
                "pattern_recognition",
                "data_analysis",
            ],
            "description": "學習器 — 從對話和任務中提取知識，驅動協調器",
            "tags": ["domain/learning", "domain/ai"],
        },
        {
            "name": "code_updater",
            "capabilities": [
                "code_analysis",
                "code_update",
                "bug_detection",
                "refactoring",
            ],
            "description": "程式碼更新智能體 — 自動偵測和修復程式碼問題",
            "tags": ["domain/python", "domain/flask", "type/code"],
        },
        {
            "name": "traffic_controller",
            "capabilities": [
                "rate_limiting",
                "load_balancing",
                "request_routing",
                "performance",
            ],
            "description": "流量控制器 — 管理 API 請求速率和模型負載",
            "tags": ["domain/performance", "domain/api"],
        },
        {
            "name": "tagger",
            "capabilities": [
                "tagging",
                "classification",
                "labeling",
                "taxonomy_management",
            ],
            "description": "標籤智能體 — 自動為所有資料打標籤，維護分類體系",
            "tags": ["domain/system", "type/knowledge"],
        },
        {
            "name": "data_seeker",
            "capabilities": [
                "data_collection",
                "web_search",
                "knowledge_retrieval",
                "rag_search",
            ],
            "description": "資料蒐集智能體 — 主動從多來源蒐集學習資料",
            "tags": ["domain/learning", "type/knowledge"],
        },
        {
            "name": "interaction_profiler",
            "capabilities": [
                "user_profiling",
                "behavior_analysis",
                "preference_learning",
                "communication_adaptation",
            ],
            "description": "互動分析智能體 — 學習用戶偏好，優化溝通策略",
            "tags": ["domain/user_interface", "domain/learning"],
        },
    ]

    def __init__(self):
        # 載入持久化資料
        stored_agents = _load(self.AGENTS_FILE, {})
        self._agents: Dict[str, AgentProfile] = {
            k: AgentProfile.from_dict(v) for k, v in stored_agents.items()
        }

        stored_tasks = _load(self.TASKS_FILE, [])
        self._tasks: Dict[str, CollaborativeTask] = {}
        for td in stored_tasks:
            t = CollaborativeTask.__new__(CollaborativeTask)
            t.__dict__.update(td)
            t.required_capabilities = td.get("required_capabilities", [])
            t.required_tags = td.get("required_tags", [])
            self._tasks[td["id"]] = t

        self.knowledge = SharedKnowledgeBase()
        self._audit: List[Dict] = _load(self.AUDIT_FILE, [])
        self._lock = threading.Lock()

        # 訊息生命週期紀錄
        stored_msgs = _load(self.MESSAGES_FILE, [])
        self._messages: Dict[str, MessageLifecycle] = {
            d["message_id"]: MessageLifecycle.from_dict(d)
            for d in stored_msgs
            if "message_id" in d
        }

        # Dead Letter Queue（超過 MAX_RETRIES 的訊息）
        self._dlq: List[Dict] = _load(self.DLQ_FILE, [])

        # 確保內建智能體存在
        self._init_builtin_agents()

        # 啟動 watchdog（daemon thread，server 關閉時自動結束）
        self._start_watchdog()

    # ── 初始化 ────────────────────────────────────────────────

    def _init_builtin_agents(self):
        for spec in self._BUILTIN_AGENTS:
            if spec["name"] not in self._agents:
                self.register_agent(
                    spec["name"],
                    spec["capabilities"],
                    spec["description"],
                    spec.get("tags", []),
                )

    # ── 智能體登記 ────────────────────────────────────────────

    def register_agent(
        self,
        name: str,
        capabilities: List[str],
        description: str = "",
        tags: List[str] = None,
    ) -> AgentProfile:
        """登記智能體，若已存在則更新能力。"""
        with self._lock:
            if name in self._agents:
                prof = self._agents[name]
                prof.capabilities.update(capabilities)
                if tags:
                    prof.tags.update(tags)
                prof.last_active = datetime.now().isoformat()
            else:
                prof = AgentProfile(name, capabilities, description, tags)
                self._agents[name] = prof
            self._flush_agents()
            self._audit_event("register", name, {"capabilities": capabilities})
        return prof

    def heartbeat(self, agent_name: str, status: str = "idle"):
        """智能體定期回報存活狀態。"""
        if agent_name in self._agents:
            self._agents[agent_name].last_active = datetime.now().isoformat()
            self._agents[agent_name].status = status

    # ── 任務委派 ──────────────────────────────────────────────

    def delegate_task(
        self,
        title: str,
        content: str,
        required_capabilities: List[str] = None,
        required_tags: List[str] = None,
        priority: int = 2,
        source_agent: str = "orchestrator",
    ) -> Optional[CollaborativeTask]:
        """
        建立協作任務並自動分派給最合適的智能體。
        回傳分派成功的任務物件，或 None（無合適智能體時）。
        """
        task = CollaborativeTask(
            title,
            content,
            required_capabilities=required_capabilities or [],
            required_tags=required_tags or [],
            priority=priority,
            source_agent=source_agent,
        )

        best = self._find_best_agent(required_capabilities or [], required_tags or [])
        if best:
            task.assign(best.name)
            best.task_count += 1
            best.last_active = datetime.now().isoformat()
            best.status = "busy"

        with self._lock:
            self._tasks[task.id] = task
            self._flush_tasks()
            self._flush_agents()
            self._audit_event(
                "delegate",
                source_agent,
                {
                    "task_id": task.id,
                    "assigned_to": task.assigned_agent,
                    "title": title,
                },
            )
        return task

    def complete_task(
        self,
        task_id: str,
        result: str = "",
        success: bool = True,
        agent_name: str = None,
    ) -> bool:
        """標記任務完成或失敗，並更新智能體統計。"""
        task = self._tasks.get(task_id)
        if not task:
            return False
        if success:
            task.complete(result)
        else:
            task.fail(result)

        # 更新智能體統計
        agent_name = agent_name or task.assigned_agent
        if agent_name and agent_name in self._agents:
            prof = self._agents[agent_name]
            if success:
                prof.success_count += 1
            prof.status = "idle"

        with self._lock:
            self._flush_tasks()
            self._flush_agents()
            self._audit_event(
                "complete",
                agent_name or "unknown",
                {
                    "task_id": task_id,
                    "success": success,
                    "result_preview": (result or "")[:100],
                },
            )
        return True

    # ── 訊息生命週期 ──────────────────────────────────────────

    def submit_message(
        self,
        payload: str,
        sender: str = "user",
        recipient: str = "dispatcher",
        context_id: str = None,
    ) -> MessageEnvelope:
        """建立訊息封裝並進入 queued 狀態，回傳 envelope 供後續追蹤。"""
        env = MessageEnvelope(payload, sender, recipient, context_id)
        lc = MessageLifecycle(env)
        with self._lock:
            self._messages[env.message_id] = lc
            self._flush_messages()
            self._audit_event(
                "msg_submit",
                sender,
                {
                    "message_id": env.message_id,
                    "recipient": recipient,
                    "context_id": env.context_id,
                },
            )
        return env

    def start_message(self, message_id: str, agent: str) -> bool:
        """將訊息標記為處理中，綁定執行智能體（mutation + flush 在同一 lock 內）。"""
        with self._lock:
            lc = self._messages.get(message_id)
            if not lc or lc.status != "queued":
                return False
            lc.start(agent)
            self._flush_messages()
            self._audit_event("msg_start", agent, {"message_id": message_id})
        return True

    def resolve_message(
        self,
        message_id: str,
        result: str,
        model_used: str = "unknown",
        agent: str = None,
    ) -> bool:
        """標記訊息完成，mutation + flush 原子執行。"""
        with self._lock:
            lc = self._messages.get(message_id)
            if not lc or lc.status != "processing":
                return False
            resp = AgentResponse(
                message_id, result, model_used, agent or lc.current_agent
            )
            lc.complete(resp)
            self._flush_messages()
            self._audit_event(
                "msg_resolve",
                agent or lc.current_agent,
                {
                    "message_id": message_id,
                    "duration_ms": lc.duration_ms,
                    "model_used": model_used,
                },
            )
        return True

    def fail_message(
        self,
        message_id: str,
        error: str,
        error_type: str = "unknown",
        agent: str = None,
    ) -> bool:
        """標記訊息失敗；超過 MAX_RETRIES 自動送進 DLQ。"""
        with self._lock:
            lc = self._messages.get(message_id)
            if not lc or lc.status not in ("queued", "processing"):
                return False
            actor = agent or lc.current_agent
            lc.fail(error, error_type)
            # 無法再重試 → 送進 Dead Letter Queue
            if not lc.can_retry:
                self._dlq.append(
                    {
                        "message_id": lc.message_id,
                        "context_id": lc.context_id,
                        "agent": actor,
                        "error": error[:300],
                        "error_type": error_type,
                        "retry_count": lc.retry_count,
                        "dead_at": datetime.now().isoformat(),
                        "snapshot": lc.to_dict(),
                    }
                )
                if len(self._dlq) > 1000:
                    self._dlq = self._dlq[-1000:]
                self._flush_dlq()
            self._flush_messages()
            self._audit_event(
                "msg_fail",
                actor,
                {
                    "message_id": message_id,
                    "error_type": error_type,
                    "error": error[:200],
                    "retry_count": lc.retry_count,
                    "can_retry": lc.can_retry,
                },
            )
        return True

    def retry_message(self, message_id: str, new_agent: str = None) -> bool:
        """將失敗訊息重置為 queued，原子執行。"""
        with self._lock:
            lc = self._messages.get(message_id)
            if not lc or not lc.can_retry:
                return False
            lc.reset_for_retry(new_agent)
            self._flush_messages()
            self._audit_event(
                "msg_retry",
                new_agent or lc.current_agent,
                {
                    "message_id": message_id,
                    "retry_count": lc.retry_count,
                },
            )
        return True

    def get_message_status(self, message_id: str) -> Optional[Dict]:
        """查詢單條訊息的完整生命週期狀態。"""
        lc = self._messages.get(message_id)
        return lc.to_dict() if lc else None

    # ── DLQ 查詢 ─────────────────────────────────────────────

    def get_dead_letters(self, limit: int = 50) -> List[Dict]:
        """回傳 Dead Letter Queue（超過 MAX_RETRIES 的訊息）。"""
        return self._dlq[-limit:]

    def requeue_dead_letter(self, message_id: str, new_agent: str = None) -> bool:
        """從 DLQ 撈回一條訊息並手動重新入隊（重置 retry_count）。"""
        entry = next((e for e in self._dlq if e["message_id"] == message_id), None)
        if not entry:
            return False
        with self._lock:
            lc = self._messages.get(message_id)
            if lc is None:
                lc = MessageLifecycle.from_dict(entry["snapshot"])
                self._messages[message_id] = lc
            lc.retry_count = 0  # 手動重置，允許再重試
            lc.status = "queued"
            lc.started_at = None
            lc.finished_at = None
            lc.duration_ms = None
            if new_agent:
                lc.current_agent = new_agent
            self._dlq = [e for e in self._dlq if e["message_id"] != message_id]
            self._flush_dlq()
            self._flush_messages()
            self._audit_event(
                "dlq_requeue", new_agent or lc.current_agent, {"message_id": message_id}
            )
        return True

    # ── Context Trace 查詢 ────────────────────────────────────

    def get_context_messages(self, context_id: str) -> List[Dict]:
        """回傳同一 context 下所有訊息，依 queued_at 排序。"""
        msgs = [m for m in self._messages.values() if m.context_id == context_id]
        return [m.to_dict() for m in sorted(msgs, key=lambda x: x.queued_at)]

    def get_context_trace(self, context_id: str) -> Dict:
        """
        回傳 context 完整因果鏈：
        timeline（依時序）+ 狀態分佈 + 總耗時 + 失敗摘要。
        """
        msgs = [m for m in self._messages.values() if m.context_id == context_id]
        msgs.sort(key=lambda x: x.queued_at)

        total_ms = sum(m.duration_ms for m in msgs if m.duration_ms)
        failed_msgs = [m for m in msgs if m.status == "failed"]
        by_status: Dict[str, int] = defaultdict(int)
        for m in msgs:
            by_status[m.status] += 1

        return {
            "context_id": context_id,
            "total_msgs": len(msgs),
            "by_status": dict(by_status),
            "total_ms": total_ms,
            "failed_count": len(failed_msgs),
            "failure_types": list({m.error_type for m in failed_msgs if m.error_type}),
            "timeline": [
                {
                    "message_id": m.message_id,
                    "agent": m.current_agent,
                    "status": m.status,
                    "duration_ms": m.duration_ms,
                    "queued_at": datetime.fromtimestamp(m.queued_at).isoformat(),
                    "error": m.error,
                }
                for m in msgs
            ],
        }

    def message_report(self, context_id: str = None, limit: int = 50) -> Dict:
        """回傳訊息生命週期統計報告，可按 context_id 過濾。"""
        msgs = list(self._messages.values())
        if context_id:
            msgs = [m for m in msgs if m.context_id == context_id]

        by_status: Dict[str, int] = defaultdict(int)
        total_duration = 0
        count_with_duration = 0
        for m in msgs:
            by_status[m.status] += 1
            if m.duration_ms is not None:
                total_duration += m.duration_ms
                count_with_duration += 1

        recent = sorted(msgs, key=lambda x: x.queued_at, reverse=True)[:limit]
        return {
            "total": len(msgs),
            "by_status": dict(by_status),
            "avg_duration_ms": round(total_duration / max(count_with_duration, 1)),
            "recent": [m.to_dict() for m in recent],
        }

    # ── 知識共享 ──────────────────────────────────────────────

    def share_knowledge(
        self,
        agent: str,
        topic: str,
        content: str,
        tags: List[str] = None,
        confidence: float = 0.8,
    ) -> str:
        """智能體貢獻知識，回傳知識 ID。"""
        kid = self.knowledge.contribute(agent, topic, content, tags, confidence)
        self._audit_event("share_knowledge", agent, {"topic": topic, "kid": kid})
        return kid

    def query_knowledge(
        self, query: str = "", tags: List[str] = None, top_k: int = 5
    ) -> List[Dict]:
        """跨智能體查詢共享知識。"""
        return self.knowledge.query(query, tags, top_k)

    # ── 協作報告 ──────────────────────────────────────────────

    def collaboration_report(self) -> Dict:
        """產出完整協作現況報告。"""
        tasks = list(self._tasks.values())
        total = len(tasks)
        by_status: Dict[str, int] = defaultdict(int)
        for t in tasks:
            by_status[t.status] += 1

        # 任務工作量排行
        workload: Dict[str, int] = defaultdict(int)
        for t in tasks:
            if t.assigned_agent:
                workload[t.assigned_agent] += 1

        return {
            "generated_at": datetime.now().isoformat(),
            "agents": {
                "total": len(self._agents),
                "active": sum(
                    1 for a in self._agents.values() if a.status != "offline"
                ),
                "top_workers": [
                    {"agent": n, "tasks": c}
                    for n, c in sorted(
                        workload.items(), key=lambda x: x[1], reverse=True
                    )[:5]
                ],
                "profiles": [a.to_dict() for a in self._agents.values()],
            },
            "tasks": {
                "total": total,
                "by_status": dict(by_status),
                "recent": [
                    t.to_dict()
                    for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)[
                        :10
                    ]
                ],
            },
            "knowledge": {
                "total_records": len(self.knowledge._records),
                "contributor_stats": self.knowledge.contributor_stats(),
            },
            "messages": self.message_report(limit=10),
            "audit_events": len(self._audit),
        }

    def agent_list(self) -> List[Dict]:
        """回傳所有智能體的簡要清單。"""
        return [a.to_dict() for a in self._agents.values()]

    def pending_tasks(self) -> List[Dict]:
        """回傳所有待執行（created / assigned）的任務。"""
        return [
            t.to_dict()
            for t in self._tasks.values()
            if t.status in ("created", "assigned")
        ]

    # ── 能力匹配 ──────────────────────────────────────────────

    def _find_best_agent(
        self, required_caps: List[str], required_tags: List[str]
    ) -> Optional[AgentProfile]:
        """
        找出最合適的智能體。
        評分 = 能力匹配數 × 3 + 標籤匹配數 × 2 - busy懲罰 + 成功率加成
        排除 offline 智能體。
        """
        req_caps = set(required_caps)
        req_tags = set(required_tags)
        scored: List[Tuple[float, AgentProfile]] = []

        for prof in self._agents.values():
            if prof.status == "offline":
                continue
            cap_score = len(prof.capabilities & req_caps) * 3
            tag_score = len(prof.tags & req_tags) * 2
            busy_penalty = -2 if prof.status == "busy" else 0
            success_bonus = prof.success_count / max(prof.task_count, 1)
            total = cap_score + tag_score + busy_penalty + success_bonus
            # 如果有明確的能力需求，必須至少匹配一項才加入候選
            if required_caps and cap_score == 0:
                continue
            scored.append((total, prof))

        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # ── 自動學習貢獻 ──────────────────────────────────────────

    def auto_share_orchestrator_insights(self, status: Dict):
        """
        讓協調器自動把學習結果貢獻進共享知識庫。
        由 AutonomousLearningOrchestrator 每輪呼叫。
        """
        topics = status.get("top_topics", [])
        style = status.get("style_hint", "")
        if topics:
            self.share_knowledge(
                agent="learner",
                topic="用戶偏好主題",
                content=f"目前最活躍的學習主題：{', '.join(topics[:8])}。建議風格：{style}",
                tags=["domain/learning", "domain/user_interface", "type/insight"],
                confidence=0.85,
            )

    # ── Watchdog（timeout 自動 fail）────────────────────────────

    def _start_watchdog(self):
        t = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="hub-watchdog"
        )
        t.start()

    def _watchdog_loop(self):
        while True:
            time.sleep(self.WATCHDOG_INTERVAL_SEC)
            try:
                self._scan_timeouts()
            except Exception:
                pass

    def _scan_timeouts(self):
        now = time.time()
        timed_out = [
            lc
            for lc in self._messages.values()
            if lc.status == "processing"
            and lc.started_at is not None
            and (now - lc.started_at) > self.PROCESSING_TIMEOUT_SEC
        ]
        for lc in timed_out:
            self.fail_message(
                lc.message_id,
                error=f"Timeout: 超過 {self.PROCESSING_TIMEOUT_SEC}s 未完成",
                error_type="timeout",
                agent=lc.current_agent,
            )

    # ── 持久化 ────────────────────────────────────────────────

    def _flush_agents(self):
        _save(self.AGENTS_FILE, {n: a.to_dict() for n, a in self._agents.items()})

    def _flush_tasks(self):
        _save(self.TASKS_FILE, [t.to_dict() for t in self._tasks.values()])

    def _flush_messages(self):
        msgs = sorted(self._messages.values(), key=lambda m: m.queued_at, reverse=True)
        _save(self.MESSAGES_FILE, [m.to_dict() for m in msgs[:5000]])

    def _flush_dlq(self):
        _save(self.DLQ_FILE, self._dlq)

    def _audit_event(self, action: str, actor: str, detail: Dict):
        event = {
            "ts": datetime.now().isoformat(),
            "action": action,
            "actor": actor,
            "detail": detail,
        }
        self._audit.append(event)
        if len(self._audit) > 5000:
            self._audit = self._audit[-5000:]
        _save(self.AUDIT_FILE, self._audit)

    def flush(self):
        """批次寫入所有持久化資料。"""
        self._flush_agents()
        self._flush_tasks()
        self._flush_messages()
        self._flush_dlq()
        self.knowledge.flush()
