"""
智能體通信層 - Agent Communication Layer
實現中樞神經和各專業智能體之間的協作與信息共享
"""

import json
import time
import sys
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime
from pathlib import Path
from enum import Enum

# 添加父目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils import TimeHelper, JsonStorage
from core.constants import LOGS_DIR


class EventType(Enum):
    """事件類型定義"""

    # 中樞神經事件
    MODEL_SELECTED = "model_selected"
    MODEL_FAILED = "model_failed"
    MODEL_RECOVERED = "model_recovered"
    HEALTH_DEGRADED = "health_degraded"

    # 代碼更新事件
    CODE_ISSUE_DETECTED = "code_issue_detected"
    CODE_UPDATE_REQUESTED = "code_update_requested"
    CODE_UPDATE_COMPLETED = "code_update_completed"
    CODE_UPDATE_FAILED = "code_update_failed"

    # 學習事件
    FEEDBACK_RECEIVED = "feedback_received"
    LEARNING_UPDATED = "learning_updated"
    PATTERN_DISCOVERED = "pattern_discovered"


KNOWN_AGENTS = frozenset(
    {
        "dispatcher",
        "researcher",
        "engineer",
        "xiaobian",
        "proclaimer",
        "whitehat",
        "learner",
        "general",
        "orchestrator",
        "system",
    }
)


class SourceType:
    """訊息來源類型"""

    AGENT_SELF = "agent_self"  # 智能體本身產生的回應
    AGENT_RELAY = "agent_relay"  # 由另一個智能體轉發
    SYSTEM = "system"  # 系統內部事件
    EXTERNAL = "external"  # 非智能體來源（需要學習）


class Message:
    """智能體消息"""

    def __init__(
        self,
        sender: str,
        receiver: str,
        event_type: EventType,
        data: Dict[str, Any],
        priority: int = 5,
        is_agent_response: bool = True,
        source_type: str = SourceType.AGENT_SELF,
    ):
        """
        Args:
            sender:            發送者名稱
            receiver:          接收者名稱（"all" 表示廣播）
            event_type:        事件類型
            data:              消息數據
            priority:          優先級（1-10，10最高）
            is_agent_response: True = 此訊息出自智能體自己的回應邏輯
                               False = 非智能體自身回應（需觸發學習）
            source_type:       來源分類，見 SourceType
        """
        self.id = f"{sender}_{int(time.time() * 1000)}"
        self.sender = sender
        self.receiver = receiver
        self.event_type = event_type
        self.data = data
        self.priority = priority
        self.timestamp = TimeHelper.now_iso()
        self.processed = False
        self.is_agent_response = is_agent_response
        self.source_type = source_type
        # 若 sender 不在已知智能體列表，自動標記為 EXTERNAL
        if sender not in KNOWN_AGENTS and source_type == SourceType.AGENT_SELF:
            self.source_type = SourceType.EXTERNAL
            self.is_agent_response = False

    @property
    def needs_learning(self) -> bool:
        """是否需要觸發學習（來源非智能體自身時）"""
        return not self.is_agent_response or self.source_type == SourceType.EXTERNAL

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "receiver": self.receiver,
            "event_type": self.event_type.value,
            "data": self.data,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "processed": self.processed,
            "is_agent_response": self.is_agent_response,
            "source_type": self.source_type,
            "needs_learning": self.needs_learning,
        }


class MessageBroker:
    """消息代理 - 管理智能體間的消息流"""

    def __init__(self):
        self.message_queue: List[Message] = []
        self.subscribers: Dict[str, List[Callable]] = {}
        self.message_history_file = LOGS_DIR / "agent_messages.json"
        self.message_history: List[dict] = []
        # 學習回調：當訊息非智能體自身回應時觸發
        self._learning_callbacks: List[Callable[[Message], None]] = []
        self._load_message_history()

    def subscribe(
        self, event_type: EventType, callback: Callable, agent_name: str = ""
    ):
        """
        訂閱事件。
        agent_name: 訂閱者的智能體名稱（用於來源驗證日誌）。
        """
        event_key = event_type.value
        if event_key not in self.subscribers:
            self.subscribers[event_key] = []
        self.subscribers[event_key].append(callback)

    def register_learning_callback(self, callback: Callable[[Message], None]):
        """註冊「需要學習」回調：當收到非智能體自身回應的訊息時觸發。"""
        self._learning_callbacks.append(callback)

    def publish(self, message: Message):
        """發佈消息，並在需要時觸發學習流程。"""
        self.message_queue.append(message)
        self._notify_subscribers(message)
        self._save_message_to_history(message)
        if message.needs_learning:
            self._trigger_learning(message)

    def _notify_subscribers(self, message: Message):
        event_key = message.event_type.value
        for callback in self.subscribers.get(event_key, []):
            try:
                callback(message)
            except Exception as e:
                print(f"❌ 訂閱者回調失敗 [{event_key}]: {e}")
        for callback in self.subscribers.get("*", []):
            try:
                callback(message)
            except Exception as e:
                print(f"❌ 廣播回調失敗: {e}")

    def _trigger_learning(self, message: Message):
        """
        當訊息來源非智能體自身時，通知所有學習回調。
        智能體應從這些訊息中學習正確的回應方式。
        """
        log = {
            "event": "needs_learning",
            "sender": message.sender,
            "source_type": message.source_type,
            "event_type": message.event_type.value,
            "timestamp": message.timestamp,
            "data_keys": list(message.data.keys()),
        }
        print(f"📚 [MessageBroker] 非智能體來源訊息，觸發學習: {log}")
        for cb in self._learning_callbacks:
            try:
                cb(message)
            except Exception as e:
                print(f"❌ 學習回調失敗: {e}")

    def _save_message_to_history(self, message: Message):
        self.message_history.append(message.to_dict())
        if len(self.message_history) > 1000:
            self.message_history = self.message_history[-1000:]
        if len(self.message_history) % 50 == 0:
            JsonStorage.save(self.message_history_file, self.message_history)

    def _load_message_history(self):
        if self.message_history_file.exists():
            try:
                self.message_history = JsonStorage.load(
                    self.message_history_file, default=[]
                )
            except Exception:
                self.message_history = []

    def get_recent_messages(
        self,
        sender: str = None,
        event_type: EventType = None,
        limit: int = 50,
        needs_learning: bool = None,
    ) -> List[dict]:
        """
        獲取最近的消息。
        needs_learning=True 可過濾出「需要學習」的訊息。
        """
        filtered = self.message_history
        if sender:
            filtered = [m for m in filtered if m["sender"] == sender]
        if event_type:
            filtered = [m for m in filtered if m["event_type"] == event_type.value]
        if needs_learning is not None:
            filtered = [
                m for m in filtered if m.get("needs_learning") == needs_learning
            ]
        return filtered[-limit:]


class CollaborationContext:
    """協作上下文 - 保存智能體間的共享信息"""

    def __init__(self):
        self.context_file = LOGS_DIR / "collaboration_context.json"
        self.context: Dict[str, Any] = {
            "last_update": None,
            "shared_insights": [],  # 共享洞察
            "code_analysis": {},  # 代碼分析結果
            "improvement_suggestions": [],  # 改進建議
            "learning_patterns": {},  # 學習模式
            "agents_status": {},  # 各智能體狀態
        }
        self._load_context()

    def _load_context(self):
        """加載協作上下文"""
        if self.context_file.exists():
            try:
                loaded = JsonStorage.load(self.context_file, default={})
                self.context.update(loaded)
            except Exception:
                pass

    def update_shared_insight(self, insight: Dict[str, Any]):
        """更新共享洞察"""
        self.context["shared_insights"].append(
            {"timestamp": TimeHelper.now_iso(), "insight": insight}
        )

        # 保持最近 100 條洞察
        if len(self.context["shared_insights"]) > 100:
            self.context["shared_insights"] = self.context["shared_insights"][-100:]

        self._save_context()

    def add_improvement_suggestion(self, suggestion: Dict[str, Any]):
        """添加改進建議"""
        self.context["improvement_suggestions"].append(
            {
                "timestamp": TimeHelper.now_iso(),
                "suggestion": suggestion,
                "status": "pending",  # pending, in_progress, completed, rejected
            }
        )
        self._save_context()

    def set_agent_status(self, agent_name: str, status: Dict[str, Any]):
        """設置智能體狀態"""
        self.context["agents_status"][agent_name] = {
            "timestamp": TimeHelper.now_iso(),
            **status,
        }
        self._save_context()

    def get_agent_status(self, agent_name: str) -> Optional[Dict]:
        """獲取智能體狀態"""
        return self.context["agents_status"].get(agent_name)

    def _save_context(self):
        """保存協作上下文"""
        self.context["last_update"] = TimeHelper.now_iso()
        JsonStorage.save(self.context_file, self.context)

    def get_all_insights(self) -> List[Dict]:
        """獲取所有洞察"""
        return self.context.get("shared_insights", [])

    def get_pending_suggestions(self) -> List[Dict]:
        """獲取待處理的建議"""
        return [
            s
            for s in self.context.get("improvement_suggestions", [])
            if s.get("status") == "pending"
        ]


class AgentRegistry:
    """智能體註冊表 - 管理所有活動的智能體"""

    def __init__(self):
        self.agents: Dict[str, Dict] = {}

    def register(self, agent_name: str, agent_type: str, capabilities: List[str]):
        """註冊智能體"""
        self.agents[agent_name] = {
            "type": agent_type,
            "capabilities": capabilities,
            "registered_at": TimeHelper.now_iso(),
            "last_activity": TimeHelper.now_iso(),
            "status": "active",
        }
        print(f"✅ 智能體已註冊: {agent_name} ({agent_type})")

    def unregister(self, agent_name: str):
        """註銷智能體"""
        if agent_name in self.agents:
            del self.agents[agent_name]
            print(f"🛑 智能體已註銷: {agent_name}")

    def get_agent_info(self, agent_name: str) -> Optional[Dict]:
        """獲取智能體信息"""
        return self.agents.get(agent_name)

    def list_agents(self) -> List[str]:
        """列出所有活動的智能體"""
        return list(self.agents.keys())

    def find_agents_by_capability(self, capability: str) -> List[str]:
        """按能力查找智能體"""
        return [
            name
            for name, info in self.agents.items()
            if capability in info["capabilities"]
        ]

    def update_activity(self, agent_name: str):
        """更新智能體活動時間"""
        if agent_name in self.agents:
            self.agents[agent_name]["last_activity"] = TimeHelper.now_iso()


# 全局通信實例
message_broker = MessageBroker()
collaboration_context = CollaborationContext()
agent_registry = AgentRegistry()
