#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VS Code 擴展通信協議
VS Code Extension Communication Protocol

功能：
- STDIO 通信協議
- WebSocket 通信協議
- 雙向訊息傳遞
- 事件訂閱系統
- 遠程過程調用 (RPC)

作者：AI 智能體
創建時間：2026-03-21
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union
from queue import Queue, Empty
import base64
import hashlib
import hmac
import secrets

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 枚舉和資料類別
# ============================================================


class MessageType(Enum):
    """訊息類型"""

    # 請求
    REQUEST = "request"
    # 回應
    RESPONSE = "response"
    # 通知
    NOTIFICATION = "notification"
    # 錯誤
    ERROR = "error"
    # 心跳
    HEARTBEAT = "heartbeat"
    # 訂閱
    SUBSCRIBE = "subscribe"
    # 取消訂閱
    UNSUBSCRIBE = "unsubscribe"


class ProtocolType(Enum):
    """協議類型"""

    STDIO = "stdio"
    WEBSOCKET = "websocket"
    TCP = "tcp"
    IPC = "ipc"


class CommandCategory(Enum):
    """命令類別"""

    # 對話
    CONVERSATION = "conversation"
    # 智能體
    AGENT = "agent"
    # 記憶
    MEMORY = "memory"
    # 檔案
    FILE = "file"
    # 執行
    EXECUTION = "execution"
    # 調試
    DEBUG = "debug"
    # 系統
    SYSTEM = "system"


@dataclass
class Message:
    """訊息"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.REQUEST
    command: str = ""
    category: CommandCategory = CommandCategory.SYSTEM
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Request:
    """請求"""

    message_id: str
    command: str
    category: CommandCategory
    params: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    """回應"""

    request_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ProtocolConfig:
    """協議配置"""

    protocol: ProtocolType = ProtocolType.STDIO
    host: str = "localhost"
    port: int = 8765
    path: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    heartbeat_interval: float = 30.0
    encoding: str = "utf-8"


@dataclass
class RPCMethod:
    """RPC 方法"""

    name: str
    handler: Callable
    param_schema: Optional[Dict[str, Any]] = None
    return_schema: Optional[Dict[str, Any]] = None
    description: str = ""
    category: CommandCategory = CommandCategory.SYSTEM


# ============================================================
# 基類和接口
# ============================================================


class MessageHandler(ABC):
    """訊息處理器基類"""

    @abstractmethod
    async def handle_message(self, message: Message) -> Optional[Message]:
        """處理訊息"""
        pass

    @abstractmethod
    async def handle_request(self, request: Request) -> Response:
        """處理請求"""
        pass

    @abstractmethod
    async def handle_notification(self, notification: Message):
        """處理通知"""
        pass


class TransportLayer(ABC):
    """傳輸層抽象類"""

    @abstractmethod
    async def connect(self) -> bool:
        """連接"""
        pass

    @abstractmethod
    async def disconnect(self):
        """斷開"""
        pass

    @abstractmethod
    async def send(self, data: Union[str, bytes]) -> bool:
        """發送"""
        pass

    @abstractmethod
    async def receive(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """接收"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """是否連接"""
        pass


# ============================================================
# STDIO 傳輸層
# ============================================================


class StdioTransport(TransportLayer):
    """
    STDIO 傳輸層

    用於 VS Code 擴展的 STDIO 通信

    數據格式：
    - 每條訊息以 Content-Length 開頭
    - 跟隨 JSON 訊息
    """

    CONTENT_LENGTH_PREFIX = "Content-Length: "
    CONTENT_LENGTH_HEADER = "Content-Type: application/vscode-jsonrpc2\n\n"

    def __init__(self, config: ProtocolConfig):
        self.config = config
        self._connected = False
        self._buffer = b""
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """連接 STDIO"""
        # STDIO 總是連接的，這裡主要驗證
        self._connected = True
        logger.info("STDIO 傳輸層已連接")
        return True

    async def disconnect(self):
        """斷開連接"""
        self._connected = False
        logger.info("STDIO 傳輸層已斷開")

    async def send(self, data: Union[str, bytes]) -> bool:
        """發送訊息"""
        if not self._connected:
            return False

        # 轉換為位元組
        if isinstance(data, str):
            data = data.encode(self.config.encoding)

        # 構建 STDIO 格式
        content_length = len(data)
        message = (
            f"{self.CONTENT_LENGTH_PREFIX}{content_length}\n"
            f"{self.CONTENT_LENGTH_HEADER}"
        ).encode(self.config.encoding) + data

        try:
            # 寫入 stdout
            sys.stdout.buffer.write(message)
            sys.stdout.buffer.flush()
            return True
        except Exception as e:
            logger.error(f"發送失敗: {e}")
            return False

    async def receive(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """接收訊息"""
        if not self._connected:
            return None

        try:
            # 讀取 Content-Length
            line = sys.stdin.readline()
            if not line:
                return None

            # 解析長度
            if not line.startswith(self.CONTENT_LENGTH_PREFIX):
                return None

            length = int(line[len(self.CONTENT_LENGTH_PREFIX) :])

            # 跳過 Content-Type 行
            sys.stdin.readline()

            # 讀取內容
            data = sys.stdin.buffer.read(length)
            return data

        except Exception as e:
            logger.error(f"接收失敗: {e}")
            return None

    def is_connected(self) -> bool:
        """是否連接"""
        return self._connected


# ============================================================
# WebSocket 傳輸層
# ============================================================


class WebSocketTransport(TransportLayer):
    """
    WebSocket 傳輸層

    用於遠程連接的 WebSocket 通信
    """

    def __init__(self, config: ProtocolConfig):
        self.config = config
        self._connected = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """連接 WebSocket"""
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.config.host, self.config.port
            )
            self._connected = True
            logger.info(f"WebSocket 已連接: {self.config.host}:{self.config.port}")
            return True
        except Exception as e:
            logger.error(f"WebSocket 連接失敗: {e}")
            return False

    async def disconnect(self):
        """斷開連接"""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._connected = False
        logger.info("WebSocket 已斷開")

    async def send(self, data: Union[str, bytes]) -> bool:
        """發送訊息"""
        if not self._connected or not self._writer:
            return False

        async with self._lock:
            try:
                if isinstance(data, str):
                    data = data.encode(self.config.encoding)

                self._writer.write(data)
                await self._writer.drain()
                return True
            except Exception as e:
                logger.error(f"發送失敗: {e}")
                return False

    async def receive(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """接收訊息"""
        if not self._connected or not self._reader:
            return None

        try:
            if timeout:
                data = await asyncio.wait_for(self._reader.read(8192), timeout=timeout)
            else:
                data = await self._reader.read(8192)

            return data if data else None
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"接收失敗: {e}")
            return None

    def is_connected(self) -> bool:
        """是否連接"""
        return self._connected


# ============================================================
# RPC 伺服器
# ============================================================


class RPCServer:
    """
    RPC 伺服器

    功能：
    - 方法註冊
    - 請求處理
    - 回應回覆
    - 錯誤處理
    """

    def __init__(self, transport: TransportLayer, config: ProtocolConfig):
        self.transport = transport
        self.config = config
        self._methods: Dict[str, RPCMethod] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    def register_method(self, method: RPCMethod):
        """註冊方法"""
        self._methods[method.name] = method
        logger.info(f"RPC 方法已註冊: {method.name}")

    def register_command(
        self,
        command: str,
        handler: Callable,
        category: CommandCategory = CommandCategory.SYSTEM,
    ):
        """註冊命令"""
        method = RPCMethod(name=command, handler=handler, category=category)
        self.register_method(method)

    async def call(
        self, command: str, params: Dict[str, Any] = None, timeout: float = None
    ) -> Any:
        """
        調用遠程方法

        Args:
            command: 命令
            params: 參數
            timeout: 超時

        Returns:
            回應數據
        """
        if params is None:
            params = {}

        timeout = timeout or self.config.timeout

        # 創建請求
        request = Request(
            message_id=str(uuid.uuid4()),
            command=command,
            category=CommandCategory.SYSTEM,
            params=params,
            timeout=timeout,
        )

        # 發送請求
        await self._send_request(request)

        # 等待回應
        future = self._pending_requests[request.message_id]

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            if response.success:
                return response.data
            else:
                raise RuntimeError(response.error or "未知錯誤")
        except asyncio.TimeoutError:
            raise TimeoutError(f"調用超時: {command}")
        finally:
            self._pending_requests.pop(request.message_id, None)

    async def _send_request(self, request: Request):
        """發送請求"""
        message = Message(
            type=MessageType.REQUEST,
            command=request.command,
            category=request.category,
            payload=request.params,
            correlation_id=request.message_id,
        )

        await self.transport.send(json.dumps(message.__dict__))

    async def start(self):
        """啟動伺服器"""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("RPC 伺服器已啟動")

    async def stop(self):
        """停止伺服器"""
        self._running = False

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("RPC 伺服器已停止")

    async def _worker(self):
        """工作線程"""
        while self._running:
            try:
                data = await self.transport.receive(timeout=1.0)

                if data:
                    # 解析訊息
                    message_dict = json.loads(data.decode(self.config.encoding))
                    message = Message(**message_dict)

                    # 處理
                    await self._handle_message(message)

            except Exception as e:
                logger.error(f"處理訊息失敗: {e}")
                await asyncio.sleep(0.1)

    async def _handle_message(self, message: Message):
        """處理訊息"""
        if message.type == MessageType.REQUEST:
            # 處理請求
            await self._handle_request(message)

        elif message.type == MessageType.RESPONSE:
            # 處理回應
            await self._handle_response(message)

        elif message.type == MessageType.NOTIFICATION:
            # 處理通知
            await self._handle_notification(message)

        elif message.type == MessageType.HEARTBEAT:
            # 處理心跳
            await self._handle_heartbeat(message)

    async def _handle_request(self, message: Message):
        """處理請求"""
        method = self._methods.get(message.command)

        if not method:
            response = Response(
                request_id=message.correlation_id or message.id,
                success=False,
                error=f"未知命令: {message.command}",
                error_code="UNKNOWN_COMMAND",
            )
        else:
            try:
                # 調用處理器
                if asyncio.iscoroutinefunction(method.handler):
                    result = await method.handler(message.payload)
                else:
                    result = method.handler(message.payload)

                response = Response(
                    request_id=message.correlation_id or message.id,
                    success=True,
                    data=result,
                )
            except Exception as e:
                response = Response(
                    request_id=message.correlation_id or message.id,
                    success=False,
                    error=str(e),
                    error_code="EXECUTION_ERROR",
                )

        # 發送回應
        await self.transport.send(json.dumps(response.__dict__))

    async def _handle_response(self, message: Message):
        """處理回應"""
        # 找到對應的請求
        request_id = message.correlation_id

        if request_id in self._pending_requests:
            future = self._pending_requests[request_id]

            # 解析回應
            response = Response(
                request_id=request_id,
                success=message.payload.get("success", True),
                data=message.payload.get("data"),
                error=message.payload.get("error"),
                error_code=message.payload.get("error_code"),
            )

            # 設置結果
            future.set_result(response)

    async def _handle_notification(self, message: Message):
        """處理通知"""
        handlers = self._event_handlers.get(message.command, [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message.payload)
                else:
                    handler(message.payload)
            except Exception as e:
                logger.error(f"處理通知失敗: {message.command} - {e}")

    async def _handle_heartbeat(self, message: Message):
        """處理心跳"""
        # 發送心跳回應
        response = Message(
            type=MessageType.HEARTBEAT,
            command="heartbeat",
            payload={"timestamp": datetime.now().isoformat()},
        )

        await self.transport.send(json.dumps(response.__dict__))

    def subscribe(self, event: str, handler: Callable):
        """訂閱事件"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable):
        """取消訂閱"""
        if event in self._event_handlers:
            self._event_handlers[event].remove(handler)


# ============================================================
# VS Code 協議包裝器
# ============================================================


class VSCodeProtocol:
    """
    VS Code 協議包裝器

    功能：
    - 統一接口
    - 命令註冊
    - 事件處理
    - 自動重連
    """

    def __init__(self, config: ProtocolConfig = None):
        self.config = config or ProtocolConfig()

        # 傳輸層
        if self.config.protocol == ProtocolType.STDIO:
            self.transport = StdioTransport(self.config)
        else:
            self.transport = WebSocketTransport(self.config)

        # RPC
        self.server: Optional[RPCServer] = None
        self._running = False

    async def connect(self) -> bool:
        """連接"""
        connected = await self.transport.connect()

        if connected:
            self.server = RPCServer(self.transport, self.config)
            self._register_default_commands()
            await self.server.start()
            self._running = True
            logger.info("VS Code 協議已連接")

        return connected

    async def disconnect(self):
        """斷開"""
        self._running = False

        if self.server:
            await self.server.stop()

        await self.transport.disconnect()
        logger.info("VS Code 協議已斷開")

    def _register_default_commands(self):
        """註冊預設命令"""
        # 對話命令
        self.server.register_command(
            "conversation.create",
            self._cmd_conversation_create,
            CommandCategory.CONVERSATION,
        )
        self.server.register_command(
            "conversation.send",
            self._cmd_conversation_send,
            CommandCategory.CONVERSATION,
        )
        self.server.register_command(
            "conversation.list",
            self._cmd_conversation_list,
            CommandCategory.CONVERSATION,
        )

        # 智能體命令
        self.server.register_command(
            "agent.state", self._cmd_agent_state, CommandCategory.AGENT
        )
        self.server.register_command(
            "agent.update", self._cmd_agent_update, CommandCategory.AGENT
        )

        # 記憶命令
        self.server.register_command(
            "memory.save", self._cmd_memory_save, CommandCategory.MEMORY
        )
        self.server.register_command(
            "memory.load", self._cmd_memory_load, CommandCategory.MEMORY
        )
        self.server.register_command(
            "memory.search", self._cmd_memory_search, CommandCategory.MEMORY
        )

        # 系統命令
        self.server.register_command(
            "system.status", self._cmd_system_status, CommandCategory.SYSTEM
        )
        self.server.register_command(
            "system.info", self._cmd_system_info, CommandCategory.SYSTEM
        )

    # 對話命令實現
    async def _cmd_conversation_create(self, params: Dict) -> Dict:
        """創建對話"""
        # 這裡會調用記憶體管理器
        return {"session_id": "new_session", "status": "created"}

    async def _cmd_conversation_send(self, params: Dict) -> Dict:
        """發送訊息"""
        return {"message_id": "msg_001", "response": "回應內容"}

    async def _cmd_conversation_list(self, params: Dict) -> Dict:
        """列出對話"""
        return {"sessions": []}

    # 智能體命令實現
    async def _cmd_agent_state(self, params: Dict) -> Dict:
        """獲取智能體狀態"""
        return {"status": "idle", "version": "1.0.0"}

    async def _cmd_agent_update(self, params: Dict) -> Dict:
        """更新智能體"""
        return {"status": "updated"}

    # 記憶命令實現
    async def _cmd_memory_save(self, params: Dict) -> Dict:
        """保存記憶"""
        return {"status": "saved"}

    async def _cmd_memory_load(self, params: Dict) -> Dict:
        """載入記憶"""
        return {"data": {}}

    async def _cmd_memory_search(self, params: Dict) -> Dict:
        """搜尋記憶"""
        return {"results": []}

    # 系統命令實現
    async def _cmd_system_status(self, params: Dict) -> Dict:
        """系統狀態"""
        return {"status": "running", "uptime": time.time(), "memory": "OK"}

    async def _cmd_system_info(self, params: Dict) -> Dict:
        """系統資訊"""
        return {"version": "1.0.0", "platform": sys.platform, "python": sys.version}

    async def call_command(self, command: str, params: Dict = None) -> Any:
        """調用命令"""
        if not self.server:
            raise RuntimeError("未連接")

        return await self.server.call(command, params or {})

    def on_event(self, event: str, handler: Callable):
        """訂閱事件"""
        if self.server:
            self.server.subscribe(event, handler)

    def is_connected(self) -> bool:
        """是否連接"""
        return self._running and self.transport.is_connected()


# ============================================================
# 便捷函數
# ============================================================


async def create_stdio_protocol() -> VSCodeProtocol:
    """創建 STDIO 協議"""
    config = ProtocolConfig(protocol=ProtocolType.STDIO)
    protocol = VSCodeProtocol(config)
    await protocol.connect()
    return protocol


async def create_websocket_protocol(
    host: str = "localhost", port: int = 8765
) -> VSCodeProtocol:
    """創建 WebSocket 協議"""
    config = ProtocolConfig(protocol=ProtocolType.WEBSOCKET, host=host, port=port)
    protocol = VSCodeProtocol(config)
    await protocol.connect()
    return protocol


# ============================================================
# 使用範例
# ============================================================


async def main_stdio():
    """STDIO 模式使用範例"""
    protocol = await create_stdio_protocol()

    # 調用命令
    result = await protocol.call_command("system.status")
    print(f"系統狀態: {result}")

    # 等待
    await asyncio.Event().wait()


async def main_websocket():
    """WebSocket 模式使用範例"""
    protocol = await create_websocket_protocol()

    # 調用命令
    result = await protocol.call_command("conversation.create", {"title": "新對話"})
    print(f"創建對話: {result}")

    # 訂閱事件
    protocol.on_event("message", lambda msg: print(f"收到訊息: {msg}"))

    # 保持運行
    await asyncio.Event().wait()


if __name__ == "__main__":
    # STDIO 模式
    asyncio.run(main_stdio())
