#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地記憶 API 系統 (Local Memory API System)

統一接口讓任何語言模型（Gemini, Claude, ChatGPT, 本地 Mistral）
都能訪問和提取本地對話記憶。

核心功能：
1. 統一記憶數據訪問
2. 跨模型對話記錄整合
3. 快速記憶檢索
4. RESTful API 接口（可選）
5. 命令行接口
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import sys
import builtins

try:
    from core.memory_layers import ThreeLayerMemory
except Exception:
    ThreeLayerMemory = None


def _safe_print(*args, **kwargs):
    """Avoid Windows cp950 encode crashes when logs contain emoji/special chars."""
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        fallback = " ".join(str(part) for part in args)
        target_encoding = (getattr(sys.stdout, "encoding", None) or "utf-8").lower()
        fallback = fallback.encode(target_encoding, errors="ignore").decode(
            target_encoding, errors="ignore"
        )
        builtins.print(fallback)


print = _safe_print


class LocalMemoryAPI:
    """本地記憶統一訪問接口"""

    @staticmethod
    def _latest_file(directory: Path, pattern: str) -> Optional[Path]:
        if not directory.exists() or not directory.is_dir():
            return None
        matches = sorted(
            (p for p in directory.glob(pattern) if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return matches[0] if matches else None

    @staticmethod
    def _first_existing(candidates: List[Path]) -> Path:
        for candidate in candidates:
            if candidate.exists():
                return candidate
        # 保留第一候選作為預設回報路徑，避免 None 破壞既有流程。
        return candidates[0]

    def __init__(self, base_dir: str = None, chatgpt_limit: int = None):
        """
        初始化本地記憶 API

        Args:
            base_dir: 基礎目錄
            chatgpt_limit: ChatGPT 對話加載限制（None = 全部加載, 0 = 不加載, >0 = 加載前 N 條）
        """
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parents[1]
        self.chatgpt_limit = chatgpt_limit  # None = 全部, 0 = 不加載, >0 = 限制數量

        # 智能緩存配置
        self._cache_layers = {
            "full": None,  # 完整數據緩存
            "paginated": {},  # 分頁緩存
            "search": {},  # 搜索結果緩存
        }
        self._cache_stats = {"hits": 0, "misses": 0, "last_clear": datetime.now()}

        conversation_log_file = self._latest_file(
            self.base_dir / "data" / "conversation_logs", "conversations_*.json"
        ) or self._latest_file(
            self.base_dir / "data_hdd_storage" / "conversation_logs",
            "conversations_*.json",
        )
        optimization_file = self._first_existing(
            [
                self.base_dir / "data" / "conversation_logs" / "optimizations.json",
                self.base_dir
                / "data_hdd_storage"
                / "conversation_logs"
                / "optimizations.json",
            ]
        )
        bug_tracker_file = self._first_existing(
            [
                self.base_dir / "data" / "conversation_logs" / "bug_tracker.json",
                self.base_dir
                / "data_hdd_storage"
                / "conversation_logs"
                / "bug_tracker.json",
            ]
        )
        daily_routine_file = self._latest_file(
            self.base_dir / "logs", "daily_routine_*.json"
        ) or self._first_existing(
            [
                self.base_dir / "logs" / "daily_routine_20260301.json",
                self.base_dir / "data_hdd_storage" / "daily_routine_20260301.json",
            ]
        )
        collaboration_context_file = self._first_existing(
            [
                self.base_dir / "500/llama32-chat/logs/collaboration_context.json",
                self.base_dir / "logs/collaboration_context.json",
            ]
        )
        agent_work_log_file = self._first_existing(
            [
                self.base_dir / "logs/agent_work_log.json",
                self.base_dir / "data_hdd_storage" / "agent_work_log.json",
            ]
        )
        knowledge_manifest_file = self._first_existing(
            [
                self.base_dir / "data/knowledge_hub/manifest.json",
                self.base_dir / "data_hdd_storage/knowledge_hub/manifest.json",
            ]
        )

        # 定義所有對話記憶存儲位置
        self.memory_sources = {
            # 當前系統記錄
            "conversation_logs": conversation_log_file
            if conversation_log_file
            else self.base_dir / "data/conversation_logs/conversations_20260301.json",
            "chat_memory": self.base_dir / "config/chat_memory.json",
            "main_conversations": self.base_dir
            / "500/llama32-chat/data/conversations.json",
            "optimizations": optimization_file,
            "bug_tracker": bug_tracker_file,
            # ChatGPT 完整數據庫 (1,324+ 條對話, 15,154+ 條消息)
            "chatgpt_database": self.base_dir
            / "500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json",
            # 知識庫與索引
            "knowledge_base": self.base_dir
            / "500/llama32-chat/data/local_knowledge/local_knowledge_base.json",
            "data_index": self.base_dir
            / "500/llama32-chat/data/local_knowledge/complete_data_index.json",
            # 會話記錄
            "sessions": self.base_dir / "500/llama32-chat/sessions",
            # 統一洞察
            "unified_insights": self.base_dir
            / "500/llama32-chat/data/unified_insights.json",
            # 協作上下文
            "collaboration_context": collaboration_context_file,
            # 每日例行記錄
            "daily_routine": daily_routine_file,
            # Agent 工作日誌
            "agent_work_log": agent_work_log_file,
            # 統一知識中樞索引
            "knowledge_hub_manifest": knowledge_manifest_file,
        }

        # ChatGPT 分片對話文件 (conversations-000.json ~ conversations-013.json)
        self.chatgpt_conversations_dir = self.base_dir / "本地/opai本地"
        self.knowledge_hub_dir = self.base_dir / "data" / "knowledge_hub"
        self.memory_layers = (
            ThreeLayerMemory(self.base_dir) if ThreeLayerMemory else None
        )

        # 緩存數據（保持向後兼容）
        self._memory_cache = None
        self._last_refresh = None
        self.cache_duration = timedelta(minutes=5)

        # 智能緩存時長配置
        self.cache_durations = {
            "full": timedelta(minutes=5),
            "paginated": timedelta(minutes=10),
            "search": timedelta(minutes=3),
        }

        print(f"✅ 本地記憶 API 已初始化")
        print(f"   基礎目錄: {self.base_dir}")
        print(f"   數據源: {len(self.memory_sources)} 個")

    def get_all_conversations(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """
        獲取所有對話記錄（包括完整 ChatGPT 數據庫）

        Args:
            refresh: 是否強制刷新緩存

        Returns:
            所有對話記錄列表
        """
        # 檢查緩存
        if not refresh and self._memory_cache and self._last_refresh:
            if datetime.now() - self._last_refresh < self.cache_duration:
                return self._memory_cache

        all_conversations = []

        # 1. 從標準源加載對話
        for source_name, source_path in self.memory_sources.items():
            # 跳過目錄類型和特殊處理的源
            if source_name in ["sessions", "chatgpt_database"]:
                continue

            if source_path.exists() and source_path.is_file():
                try:
                    with open(source_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # 標準化數據格式
                    conversations = self._standardize_format(data, source_name)
                    all_conversations.extend(conversations)

                except Exception as e:
                    print(f"⚠️  讀取 {source_name} 時出錯: {e}")

        # 2. 加載 ChatGPT 完整數據庫 (大文件，特殊處理)
        chatgpt_db = self.memory_sources.get("chatgpt_database")
        if chatgpt_db and chatgpt_db.exists() and self.chatgpt_limit != 0:
            try:
                print("📦 加載 ChatGPT 完整數據庫 (47MB)...")
                with open(chatgpt_db, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 提取對話
                if "data" in data and "conversations" in data["data"]:
                    conversations = data["data"]["conversations"]
                    total_available = len(conversations)

                    # 根據 chatgpt_limit 決定加載數量
                    if self.chatgpt_limit is None:
                        # 加載全部
                        conversations_to_load = conversations
                        print(f"  📊 加載全部 {total_available} 條 ChatGPT 對話...")
                    else:
                        # 加載限制數量
                        conversations_to_load = conversations[: self.chatgpt_limit]
                        print(
                            f"  📊 加載前 {self.chatgpt_limit} 條 ChatGPT 對話（共 {total_available} 條）..."
                        )

                    # 標準化並添加對話
                    loaded_count = 0
                    for conv in conversations_to_load:
                        standardized = self._standardize_chatgpt_conversation(conv)
                        if standardized:
                            all_conversations.append(standardized)
                            loaded_count += 1

                    print(
                        f"  ✅ 成功加載 {loaded_count}/{total_available} 條 ChatGPT 對話"
                    )

            except Exception as e:
                print(f"⚠️  加載 ChatGPT 數據庫時出錯: {e}")

        # 3. 加載 sessions 目錄
        sessions_dir = self.memory_sources.get("sessions")
        if sessions_dir and sessions_dir.exists() and sessions_dir.is_dir():
            try:
                for session_file in sessions_dir.glob("*.json"):
                    with open(session_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    conversations = self._standardize_format(
                        data, f"session_{session_file.stem}"
                    )
                    all_conversations.extend(conversations)
            except Exception as e:
                print(f"⚠️  加載 sessions 時出錯: {e}")

        # 按時間戳排序（處理混合類型 - 統一轉換為浮點數）
        def get_sort_key(conv):
            timestamp = conv.get("timestamp", 0)
            try:
                if isinstance(timestamp, (int, float)):
                    return float(timestamp)
                elif isinstance(timestamp, str) and timestamp:
                    # 嘗試多種格式
                    if (
                        timestamp.replace(".", "")
                        .replace("-", "")
                        .replace(":", "")
                        .replace("T", "")
                        .isdigit()
                    ):
                        # 可能是數字字符串
                        return float(
                            timestamp.replace("-", "")
                            .replace(":", "")
                            .replace("T", "")[:14]
                        )
                    else:
                        # ISO 格式或其他，返回一個較大的數（保持在最前）
                        return 9999999999.0
                return 0.0
            except:
                return 0.0

        all_conversations.sort(key=get_sort_key, reverse=True)

        # 更新緩存
        self._memory_cache = all_conversations
        self._last_refresh = datetime.now()

        return all_conversations

    def _standardize_chatgpt_conversation(self, conv: Dict) -> Optional[Dict[str, Any]]:
        """
        標準化 ChatGPT 導出的對話格式

        Args:
            conv: ChatGPT 對話原始數據

        Returns:
            標準化的對話字典
        """
        try:
            # 提取對話 ID 和標題
            conv_id = conv.get("id", conv.get("conversation_id", "unknown"))
            title = conv.get("title", "Untitled Conversation")

            # 提取消息
            messages = []
            mapping = conv.get("mapping", {})
            for msg_id, msg_data in mapping.items():
                message = msg_data.get("message")
                if message:
                    role = message.get("author", {}).get("role", "unknown")
                    content = message.get("content", {})

                    # 提取文本內容
                    text_parts = []
                    if isinstance(content, dict) and "parts" in content:
                        for part in content["parts"]:
                            if isinstance(part, str):
                                text_parts.append(part)

                    if text_parts:
                        messages.append(
                            {"role": role, "content": "\n".join(text_parts)}
                        )

            if not messages:
                return None

            # 組合用戶輸入和助手回應
            user_inputs = [m["content"] for m in messages if m["role"] == "user"]
            assistant_responses = [
                m["content"] for m in messages if m["role"] == "assistant"
            ]

            return {
                "id": f"chatgpt_{conv_id}",
                "timestamp": str(conv.get("create_time", "")),
                "title": title,
                "user_input": "\n---\n".join(user_inputs) if user_inputs else "",
                "assistant_response": "\n---\n".join(assistant_responses)
                if assistant_responses
                else "",
                "metadata": {
                    "source": "chatgpt",
                    "conversation_id": conv_id,
                    "message_count": len(messages),
                },
                "source": "chatgpt_database",
            }

        except Exception as e:
            print(f"⚠️  解析 ChatGPT 對話時出錯: {e}")
            return None

    def _standardize_format(self, data: Any, source: str) -> List[Dict[str, Any]]:
        """
        標準化不同來源的數據格式

        Args:
            data: 原始數據
            source: 數據源名稱

        Returns:
            標準化的對話列表
        """
        standardized = []

        if isinstance(data, list):
            # 已經是列表格式
            for item in data:
                item["source"] = source
                standardized.append(item)

        elif isinstance(data, dict):
            if "conversations" in data:
                # config/chat_memory.json 格式
                for conv in data.get("conversations", []):
                    standardized.append(
                        {
                            "id": f"{source}_{len(standardized)}",
                            "timestamp": conv.get("timestamp", ""),
                            "user_input": conv.get("user", ""),
                            "assistant_response": conv.get("ai", ""),
                            "metadata": {"api_used": conv.get("api_used", "unknown")},
                            "source": source,
                        }
                    )

            elif "bugs" in data or "optimizations" in data:
                # bug_tracker.json 或 optimizations.json
                items = data.get("bugs", data.get("optimizations", []))
                for item in items:
                    standardized.append(
                        {
                            "id": item.get("id", f"{source}_{len(standardized)}"),
                            "timestamp": item.get("timestamp", ""),
                            "content": item,
                            "type": "system_record",
                            "source": source,
                        }
                    )

        return standardized

    def search_conversations(
        self,
        query: str = None,
        start_date: str = None,
        end_date: str = None,
        source: str = None,
        limit: int = 50,
        auto_expand: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        搜索對話記錄（支持自動擴展搜索範圍）

        Args:
            query: 搜索關鍵詞（在用戶輸入和助手回應中搜索）
            start_date: 開始日期 (YYYY-MM-DD)
            end_date: 結束日期 (YYYY-MM-DD)
            source: 指定數據源
            limit: 最大返回數量
            auto_expand: 當結果少於 limit/2 時自動擴展到完整數據庫搜索

        Returns:
            符合條件的對話列表
        """
        # 檢查搜索緩存
        cache_key = f"{query}_{start_date}_{end_date}_{source}_{limit}"
        if cache_key in self._cache_layers["search"]:
            cached_data, cached_time = self._cache_layers["search"][cache_key]
            if datetime.now() - cached_time < self.cache_durations["search"]:
                self._cache_stats["hits"] += 1
                return cached_data

        self._cache_stats["misses"] += 1

        # 首次使用默認加載（性能優化）
        all_conversations = self.get_all_conversations()
        results = []

        for conv in all_conversations:
            # 源過濾
            if source and conv.get("source") != source:
                continue

            # 日期過濾
            timestamp = conv.get("timestamp", "")
            if start_date and timestamp < start_date:
                continue
            if end_date and timestamp > end_date:
                continue

            # 關鍵詞搜索
            if query:
                user_input = conv.get("user_input", "")
                assistant_response = conv.get("assistant_response", "")
                content = conv.get("content", "")

                search_text = (
                    f"{user_input} {assistant_response} {str(content)}".lower()
                )
                if query.lower() not in search_text:
                    continue

            results.append(conv)

            if len(results) >= limit:
                break

        # 自動擴展：如果結果少於期望的一半，且開啟自動擴展
        if auto_expand and len(results) < limit / 2 and self.chatgpt_limit is not None:
            print(f"  🔍 搜索結果僅 {len(results)} 條，自動擴展到完整數據庫...")
            # 重新加載完整數據
            original_limit = self.chatgpt_limit
            self.chatgpt_limit = None  # 臨時設置為無限制
            all_conversations = self.get_all_conversations(refresh=True)
            self.chatgpt_limit = original_limit  # 恢復原設置

            # 重新搜索
            results = []
            for conv in all_conversations:
                if source and conv.get("source") != source:
                    continue
                if start_date and timestamp < start_date:
                    continue
                if end_date and timestamp > end_date:
                    continue

                if query:
                    user_input = conv.get("user_input", "")
                    assistant_response = conv.get("assistant_response", "")
                    content = conv.get("content", "")
                    search_text = (
                        f"{user_input} {assistant_response} {str(content)}".lower()
                    )
                    if query.lower() not in search_text:
                        continue

                results.append(conv)
                if len(results) >= limit:
                    break

            print(f"  ✅ 擴展後找到 {len(results)} 條結果")

        # 緩存搜索結果
        self._cache_layers["search"][cache_key] = (results, datetime.now())

        return results

    def get_latest_conversations(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        獲取最新的 N 條對話

        Args:
            count: 返回數量

        Returns:
            最新對話列表
        """
        all_conversations = self.get_all_conversations()
        return all_conversations[:count]

    def get_conversations_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        source: str = None,
        date_filter: str = None,
    ) -> Dict[str, Any]:
        """
        分頁獲取對話記錄（中期改進 #1）

        Args:
            page: 頁碼（從 1 開始）
            page_size: 每頁數量
            source: 過濾數據源
            date_filter: 日期過濾 (YYYY-MM-DD)

        Returns:
            分頁結果字典，包含 data, total, page, page_size, total_pages
        """
        # 檢查分頁緩存
        cache_key = f"page_{page}_{page_size}_{source}_{date_filter}"
        if cache_key in self._cache_layers["paginated"]:
            cached_data, cached_time = self._cache_layers["paginated"][cache_key]
            if datetime.now() - cached_time < self.cache_durations["paginated"]:
                self._cache_stats["hits"] += 1
                return cached_data

        self._cache_stats["misses"] += 1

        # 獲取所有對話
        all_conversations = self.get_all_conversations()

        # 應用過濾器
        filtered = []
        for conv in all_conversations:
            if source and conv.get("source") != source:
                continue
            if date_filter:
                timestamp = str(conv.get("timestamp", ""))
                if not timestamp.startswith(date_filter):
                    continue
            filtered.append(conv)

        # 計算分頁
        total = len(filtered)
        total_pages = (total + page_size - 1) // page_size  # 向上取整
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        # 獲取當前頁數據
        page_data = filtered[start_idx:end_idx]

        result = {
            "data": page_data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "metadata": {
                "source_filter": source,
                "date_filter": date_filter,
                "timestamp": datetime.now().isoformat(),
            },
        }

        # 緩存分頁結果
        self._cache_layers["paginated"][cache_key] = (result, datetime.now())

        return result

    def get_memory_summary(self) -> Dict[str, Any]:
        """
        獲取記憶系統總結（包括完整統計）

        Returns:
            記憶統計信息
        """
        all_conversations = self.get_all_conversations()

        # 按源分類統計
        by_source = defaultdict(int)
        by_date = defaultdict(int)

        for conv in all_conversations:
            source = conv.get("source", "unknown")
            by_source[source] += 1

            timestamp = conv.get("timestamp", "")
            if timestamp:
                try:
                    # 嘗試提取日期
                    if isinstance(timestamp, (int, float)):
                        date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                    else:
                        date = str(timestamp)[:10]  # YYYY-MM-DD
                    by_date[date] += 1
                except:
                    pass

        # 獲取 ChatGPT 完整數據庫統計
        chatgpt_stats = self._get_chatgpt_full_stats()

        summary = {
            "total_conversations_loaded": len(all_conversations),
            "by_source": dict(by_source),
            "by_date": dict(sorted(by_date.items(), reverse=True)[:7]),  # 最近 7 天
            "data_sources": list(self.memory_sources.keys()),
            "last_refresh": self._last_refresh.isoformat()
            if self._last_refresh
            else None,
            # ChatGPT 完整統計
            "chatgpt_full_database": chatgpt_stats,
            # 總計
            "total_available_conversations": chatgpt_stats.get("total_conversations", 0)
            + len(all_conversations),
            "total_messages": chatgpt_stats.get("total_messages", 0),
            "note": "為提高性能，當前僅加載前 100 條 ChatGPT 對話。使用 --full 標誌加載全部。",
        }

        return summary

    def _get_chatgpt_full_stats(self) -> Dict[str, Any]:
        """
        獲取 ChatGPT 完整數據庫統計

        Returns:
            統計信息字典
        """
        stats = {
            "total_conversations": 0,
            "total_messages": 0,
            "group_chats": 0,
            "shared_conversations": 0,
            "sora_generations": 0,
            "dalle_generations": 0,
            "attachments": 0,
        }

        # 讀取數據索引
        data_index = self.memory_sources.get("data_index")
        if data_index and data_index.exists():
            try:
                with open(data_index, "r", encoding="utf-8") as f:
                    index_data = json.load(f)

                data_types = index_data.get("data_types", {})
                stats["total_conversations"] = data_types.get("conversations", {}).get(
                    "count", 0
                )
                stats["total_messages"] = data_types.get("messages", {}).get("count", 0)
                stats["group_chats"] = data_types.get("group_chats", {}).get("count", 0)
                stats["shared_conversations"] = data_types.get(
                    "shared_conversations", {}
                ).get("count", 0)
                stats["sora_generations"] = data_types.get("sora_generations", {}).get(
                    "count", 0
                )
                stats["dalle_generations"] = data_types.get(
                    "dalle_generations", {}
                ).get("count", 0)

                # 附件數量
                attachments_str = data_types.get("attachments", {}).get("count", "0")
                if isinstance(attachments_str, str) and "+" in attachments_str:
                    stats["attachments"] = int(attachments_str.split("+")[0])
                else:
                    stats["attachments"] = int(attachments_str)

            except Exception as e:
                print(f"⚠️  讀取 ChatGPT 統計時出錯: {e}")

        return stats

    def get_knowledge_hub_status(self) -> Dict[str, Any]:
        """
        取得統一知識中樞狀態。

        Returns:
            知識中樞 manifest 與主要來源概況
        """
        manifest_path = self.knowledge_hub_dir / "manifest.json"
        status: Dict[str, Any] = {
            "path": str(self.knowledge_hub_dir),
            "exists": self.knowledge_hub_dir.exists(),
            "manifest_path": str(manifest_path),
            "manifest_exists": manifest_path.exists(),
        }

        if manifest_path.exists():
            try:
                status["manifest"] = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except Exception as e:
                status["manifest_error"] = str(e)

        return status

    def get_long_term_memory_status(self) -> Dict[str, Any]:
        if not self.memory_layers:
            return {"available": False, "reason": "ThreeLayerMemory 未載入"}
        stats = self.memory_layers.stats()
        stats["available"] = True
        return stats

    def search_long_term_memory(
        self, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        if not self.memory_layers:
            return []
        return self.memory_layers.search(query, top_k=top_k)

    def clear_cache(self, cache_type: str = "all") -> Dict[str, Any]:
        """
        清除緩存（中期改進 #3：智能緩存管理）

        Args:
            cache_type: 緩存類型 ('all', 'full', 'paginated', 'search')

        Returns:
            清除統計信息
        """
        cleared = []

        if cache_type in ["all", "full"]:
            if self._memory_cache:
                cleared.append("full")
                self._memory_cache = None
                self._last_refresh = None
            if self._cache_layers["full"]:
                self._cache_layers["full"] = None

        if cache_type in ["all", "paginated"]:
            count = len(self._cache_layers["paginated"])
            self._cache_layers["paginated"] = {}
            if count > 0:
                cleared.append(f"paginated({count})")

        if cache_type in ["all", "search"]:
            count = len(self._cache_layers["search"])
            self._cache_layers["search"] = {}
            if count > 0:
                cleared.append(f"search({count})")

        self._cache_stats["last_clear"] = datetime.now()

        return {
            "cleared": cleared,
            "cache_stats": self.get_cache_stats(),
            "timestamp": datetime.now().isoformat(),
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        獲取緩存統計信息（中期改進 #3）

        Returns:
            緩存統計字典
        """
        hit_rate = 0
        total_requests = self._cache_stats["hits"] + self._cache_stats["misses"]
        if total_requests > 0:
            hit_rate = (self._cache_stats["hits"] / total_requests) * 100

        return {
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "hit_rate": f"{hit_rate:.1f}%",
            "cached_items": {
                "full": 1 if self._memory_cache else 0,
                "paginated": len(self._cache_layers["paginated"]),
                "search": len(self._cache_layers["search"]),
            },
            "last_clear": self._cache_stats["last_clear"].isoformat(),
        }

    def get_statistics_dashboard(self) -> Dict[str, Any]:
        """
        獲取統計儀表板數據（中期改進 #4）

        Returns:
            完整的統計儀表板數據
        """
        all_conversations = self.get_all_conversations()

        # 基本統計
        total_conversations = len(all_conversations)

        # 按來源統計
        source_stats = defaultdict(int)
        for conv in all_conversations:
            source_stats[conv.get("source", "unknown")] += 1

        # 按日期統計（最近30天）
        date_stats = defaultdict(int)
        for conv in all_conversations:
            timestamp = conv.get("timestamp", "")
            try:
                if isinstance(timestamp, (int, float)):
                    date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                else:
                    date = str(timestamp)[:10]
                date_stats[date] += 1
            except:
                pass

        recent_dates = dict(sorted(date_stats.items(), reverse=True)[:30])

        # 消息長度分析
        message_lengths = []
        for conv in all_conversations[:100]:  # 採樣前100條
            user_input = conv.get("user_input", "")
            assistant_response = conv.get("assistant_response", "")
            if user_input:
                message_lengths.append(len(user_input))
            if assistant_response:
                message_lengths.append(len(assistant_response))

        avg_length = (
            sum(message_lengths) / len(message_lengths) if message_lengths else 0
        )

        # 數據質量評估
        quality_stats = {
            "with_user_input": sum(1 for c in all_conversations if c.get("user_input")),
            "with_assistant_response": sum(
                1 for c in all_conversations if c.get("assistant_response")
            ),
            "with_timestamp": sum(1 for c in all_conversations if c.get("timestamp")),
            "completeness_rate": 0,
        }

        if total_conversations > 0:
            completeness = (
                quality_stats["with_user_input"]
                + quality_stats["with_assistant_response"]
            )
            quality_stats["completeness_rate"] = (
                f"{(completeness / (total_conversations * 2)) * 100:.1f}%"
            )

        # ChatGPT 完整數據庫統計
        chatgpt_full_stats = self._get_chatgpt_full_stats()

        dashboard = {
            "overview": {
                "total_conversations_loaded": total_conversations,
                "total_conversations_available": chatgpt_full_stats.get(
                    "total_conversations", 0
                )
                + total_conversations,
                "total_messages": chatgpt_full_stats.get("total_messages", 0),
                "data_sources_count": len(self.memory_sources),
            },
            "by_source": dict(
                sorted(source_stats.items(), key=lambda x: x[1], reverse=True)
            ),
            "time_series": {"recent_30_days": recent_dates},
            "message_analysis": {
                "average_message_length": int(avg_length),
                "sampled_messages": len(message_lengths),
            },
            "data_quality": quality_stats,
            "chatgpt_database": chatgpt_full_stats,
            "knowledge_hub": self.get_knowledge_hub_status(),
            "long_term_memory": self.get_long_term_memory_status(),
            "cache_performance": self.get_cache_stats(),
            "system_info": {
                "chatgpt_load_limit": self.chatgpt_limit
                if self.chatgpt_limit
                else "unlimited",
                "cache_duration_minutes": int(self.cache_duration.total_seconds() / 60),
                "last_refresh": self._last_refresh.isoformat()
                if self._last_refresh
                else None,
            },
            "generated_at": datetime.now().isoformat(),
        }

        return dashboard

    def export_for_model(
        self,
        model_type: str = "openai",
        recent_count: int = 20,
        include_metadata: bool = False,
    ) -> str:
        """
        為特定模型導出記憶數據

        Args:
            model_type: 模型類型 (openai, anthropic, google, local)
            recent_count: 最近對話數量
            include_metadata: 是否包含元數據

        Returns:
            格式化的記憶文本
        """
        conversations = self.get_latest_conversations(recent_count)

        if model_type == "openai":
            # OpenAI 格式
            messages = []
            for conv in conversations:
                if conv.get("user_input"):
                    messages.append({"role": "user", "content": conv["user_input"]})
                if conv.get("assistant_response"):
                    messages.append(
                        {"role": "assistant", "content": conv["assistant_response"]}
                    )
            return json.dumps(messages, ensure_ascii=False, indent=2)

        elif model_type == "anthropic":
            # Claude 格式
            text = "以下是用戶的對話記憶：\n\n"
            for i, conv in enumerate(conversations, 1):
                text += f"對話 {i}:\n"
                if conv.get("user_input"):
                    text += f"用戶: {conv['user_input']}\n"
                if conv.get("assistant_response"):
                    text += f"助手: {conv['assistant_response']}\n"
                text += "\n"
            return text

        elif model_type == "google":
            # Gemini 格式
            parts = []
            for conv in conversations:
                if conv.get("user_input"):
                    parts.append(
                        {"role": "user", "parts": [{"text": conv["user_input"]}]}
                    )
                if conv.get("assistant_response"):
                    parts.append(
                        {
                            "role": "model",
                            "parts": [{"text": conv["assistant_response"]}],
                        }
                    )
            return json.dumps({"contents": parts}, ensure_ascii=False, indent=2)

        else:  # local or default
            # 通用文本格式
            text = "=== 本地對話記憶 ===\n\n"
            for i, conv in enumerate(conversations, 1):
                text += f"[{conv.get('timestamp', 'N/A')}]\n"
                text += f"用戶: {conv.get('user_input', 'N/A')}\n"
                text += f"助手: {conv.get('assistant_response', 'N/A')}\n"

                if include_metadata and conv.get("metadata"):
                    text += (
                        f"元數據: {json.dumps(conv['metadata'], ensure_ascii=False)}\n"
                    )

                text += "\n" + "-" * 60 + "\n\n"

            return text

    def test_ollama_connection(self) -> Dict[str, Any]:
        """
        測試本地 Ollama 模型連接

        Returns:
            連接測試結果
        """
        import subprocess

        result = {
            "ollama_installed": False,
            "models_available": [],
            "connection_status": "unknown",
        }

        try:
            # 檢查 Ollama 是否安裝
            check = subprocess.run(
                ["which", "ollama"], capture_output=True, text=True, timeout=5
            )

            if check.returncode == 0:
                result["ollama_installed"] = True

                # 獲取可用模型
                models = subprocess.run(
                    ["ollama", "list"], capture_output=True, text=True, timeout=10
                )

                if models.returncode == 0:
                    lines = models.stdout.strip().split("\n")[1:]  # 跳過標題行
                    result["models_available"] = [
                        line.split()[0] for line in lines if line.strip()
                    ]
                    result["connection_status"] = "connected"

        except Exception as e:
            result["connection_status"] = f"error: {str(e)}"

        return result


def main():
    """命令行接口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="本地記憶 API - 統一訪問接口（含中期改進）"
    )
    parser.add_argument("--summary", action="store_true", help="顯示記憶總結")
    parser.add_argument("--latest", type=int, default=10, help="顯示最新 N 條對話")
    parser.add_argument("--search", type=str, help="搜索關鍵詞")
    parser.add_argument(
        "--export",
        type=str,
        choices=["openai", "anthropic", "google", "local"],
        help="為指定模型導出數據",
    )
    parser.add_argument("--test-ollama", action="store_true", help="測試 Ollama 連接")
    parser.add_argument(
        "--full",
        action="store_true",
        help="加載全部 1,324 條 ChatGPT 對話（默認只加載 100 條以提高性能）",
    )
    parser.add_argument(
        "--chatgpt-limit",
        type=int,
        default=100,
        help="ChatGPT 對話加載數量（默認 100，使用 0 跳過，使用 --full 加載全部）",
    )

    # 中期改進功能
    parser.add_argument("--page", type=int, help="分頁查詢：頁碼")
    parser.add_argument("--page-size", type=int, default=50, help="分頁查詢：每頁數量")
    parser.add_argument("--dashboard", action="store_true", help="顯示統計儀表板")
    parser.add_argument("--cache-stats", action="store_true", help="顯示緩存統計")
    parser.add_argument(
        "--clear-cache",
        type=str,
        choices=["all", "full", "paginated", "search"],
        help="清除緩存",
    )

    args = parser.parse_args()

    # 確定 ChatGPT 加載限制
    if args.full:
        chatgpt_limit = None  # 加載全部
    else:
        chatgpt_limit = args.chatgpt_limit

    api = LocalMemoryAPI(chatgpt_limit=chatgpt_limit)

    if args.dashboard:
        print("\n📊 統計儀表板")
        print("=" * 70)
        dashboard = api.get_statistics_dashboard()
        print(json.dumps(dashboard, ensure_ascii=False, indent=2))

    elif args.cache_stats:
        print("\n💾 緩存統計")
        print("=" * 70)
        stats = api.get_cache_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    elif args.clear_cache:
        print(f"\n🗑️  清除緩存: {args.clear_cache}")
        print("=" * 70)
        result = api.clear_cache(args.clear_cache)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.page:
        print(f"\n📄 分頁查詢 - 第 {args.page} 頁")
        print("=" * 70)
        result = api.get_conversations_paginated(
            page=args.page, page_size=args.page_size
        )
        print(f"\n分頁信息:")
        print(json.dumps(result["pagination"], ensure_ascii=False, indent=2))
        print(f"\n顯示 {len(result['data'])} 條對話:")
        for i, conv in enumerate(result["data"][:5], 1):
            print(f"\n{i}. [{conv.get('source')}] {conv.get('timestamp', 'N/A')[:10]}")
            print(f"   {conv.get('user_input', 'N/A')[:80]}...")

    elif args.summary:
        print("\n📊 記憶系統總結")
        print("=" * 70)
        summary = api.get_memory_summary()
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    elif args.search:
        print(f"\n🔍 搜索結果: '{args.search}'")
        print("=" * 70)
        results = api.search_conversations(query=args.search)
        print(f"找到 {len(results)} 條記錄\n")
        for conv in results[:5]:
            print(f"[{conv.get('timestamp', 'N/A')}]")
            print(f"用戶: {conv.get('user_input', 'N/A')[:100]}...")
            print(f"助手: {conv.get('assistant_response', 'N/A')[:100]}...")
            print("-" * 70)

    elif args.export:
        print(f"\n📤 導出為 {args.export} 格式")
        print("=" * 70)
        exported = api.export_for_model(
            model_type=args.export, recent_count=args.latest
        )
        print(exported)

    elif args.test_ollama:
        print("\n🔌 測試 Ollama 連接")
        print("=" * 70)
        result = api.test_ollama_connection()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print(f"\n💬 最新 {args.latest} 條對話")
        print("=" * 70)
        conversations = api.get_latest_conversations(args.latest)
        for i, conv in enumerate(conversations, 1):
            print(f"\n[{i}] {conv.get('timestamp', 'N/A')}")
            print(f"用戶: {conv.get('user_input', 'N/A')[:150]}")
            print(f"助手: {conv.get('assistant_response', 'N/A')[:150]}")
            print("-" * 70)


if __name__ == "__main__":
    main()
