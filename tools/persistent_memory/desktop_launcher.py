#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面啟動器架構重構
Desktop Launcher Architecture Refactoring

功能：
- 分散式平台架構
- 浮動視窗支援
- 熱插拔插件系統
- 系統匣整合
- 多視窗管理

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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union
from queue import Queue, Empty
import subprocess

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 枚舉和資料類別
# ============================================================


class WindowType(Enum):
    """視窗類型"""

    MAIN = "main"
    FLOATING = "floating"
    POPUP = "popup"
    TOOL = "tool"
    SETTINGS = "settings"
    NOTIFICATION = "notification"


class PluginState(Enum):
    """插件狀態"""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ACTIVE = "active"
    ERROR = "error"
    UNINSTALLING = "uninstalling"


class LaunchMode(Enum):
    """啟動模式"""

    NORMAL = "normal"
    MINIMIZED = "minimized"
    BACKGROUND = "background"
    TRAY = "tray"


@dataclass
class WindowConfig:
    """視窗配置"""

    window_id: str
    title: str
    window_type: WindowType
    width: int = 800
    height: int = 600
    x: int = 100
    y: int = 100
    resizable: bool = True
    always_on_top: bool = False
    opacity: float = 1.0
    decorations: bool = True
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginInfo:
    """插件資訊"""

    plugin_id: str
    name: str
    version: str
    author: str
    description: str
    entry_point: str
    dependencies: List[str] = field(default_factory=list)
    state: PluginState = PluginState.UNLOADED
    load_time: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LaunchConfig:
    """啟動配置"""

    mode: LaunchMode = LaunchMode.NORMAL
    workspace_path: Optional[str] = None
    persistent_memory_enabled: bool = True
    auto_restore_session: bool = True
    max_windows: int = 10
    plugin_dirs: List[str] = field(default_factory=lambda: ["plugins", "data/plugins"])
    log_level: str = "INFO"
    debug_mode: bool = False


@dataclass
class SystemTrayItem:
    """系統匣項目"""

    item_id: str
    label: str
    icon: Optional[str] = None
    action: Optional[Callable] = None
    submenu: List["SystemTrayItem"] = field(default_factory=list)
    separator: bool = False
    enabled: bool = True


# ============================================================
# 基礎接口
# ============================================================


class PluginBase(ABC):
    """插件基類"""

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """插件 ID"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """插件名稱"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """版本"""
        pass

    @abstractmethod
    def initialize(self, context: "PluginContext") -> bool:
        """初始化"""
        pass

    @abstractmethod
    def activate(self):
        """啟動"""
        pass

    @abstractmethod
    def deactivate(self):
        """停用"""
        pass

    @abstractmethod
    def cleanup(self):
        """清理"""
        pass


class PluginContext:
    """插件上下文"""

    def __init__(self, launcher: "DesktopLauncher"):
        self.launcher = launcher
        self.storage = launcher.memory_manager
        self.config = launcher.config
        self._resources: Dict[str, Any] = {}

    def register_resource(self, key: str, resource: Any):
        """註冊資源"""
        self._resources[key] = resource

    def get_resource(self, key: str) -> Optional[Any]:
        """取得資源"""
        return self._resources.get(key)

    def emit_event(self, event_type: str, data: Any):
        """發射事件"""
        self.launcher.emit_event(event_type, data, self)


# ============================================================
# 插件管理器
# ============================================================


class PluginManager:
    """
    插件管理器

    功能：
    - 插件載入/卸載
    - 依賴解析
    - 生命週期管理
    - 版本控制
    """

    def __init__(self, launcher: "DesktopLauncher"):
        self.launcher = launcher
        self._plugins: Dict[str, PluginBase] = {}
        self._plugin_info: Dict[str, PluginInfo] = {}
        self._dependencies: Dict[str, Set[str]] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()

    async def discover_plugins(self, plugin_dirs: List[str]) -> List[PluginInfo]:
        """
        發現插件

        Args:
            plugin_dirs: 插件目錄列表

        Returns:
            插件資訊列表
        """
        discovered = []

        for plugin_dir in plugin_dirs:
            if not os.path.exists(plugin_dir):
                continue

            # 掃描插件
            for entry in os.listdir(plugin_dir):
                plugin_path = os.path.join(plugin_dir, entry)

                # 檢查是否為插件目錄
                if not os.path.isdir(plugin_path):
                    continue

                # 檢查 plugin.json
                manifest_path = os.path.join(plugin_path, "plugin.json")
                if not os.path.exists(manifest_path):
                    continue

                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)

                    info = PluginInfo(
                        plugin_id=manifest.get("id", entry),
                        name=manifest.get("name", entry),
                        version=manifest.get("version", "1.0.0"),
                        author=manifest.get("author", "Unknown"),
                        description=manifest.get("description", ""),
                        entry_point=manifest.get("entry", "main.py"),
                        dependencies=manifest.get("dependencies", []),
                    )
                    discovered.append(info)

                except Exception as e:
                    logger.warning(f"載入插件清單失敗: {entry} - {e}")

        return discovered

    async def load_plugin(self, plugin_info: PluginInfo) -> bool:
        """
        載入插件

        Args:
            plugin_info: 插件資訊

        Returns:
            是否成功
        """
        async with self._lock:
            # 檢查是否已載入
            if plugin_info.plugin_id in self._plugins:
                logger.warning(f"插件已載入: {plugin_info.plugin_id}")
                return True

            # 檢查依賴
            for dep in plugin_info.dependencies:
                if dep not in self._plugins:
                    logger.error(f"缺少依賴: {plugin_info.plugin_id} -> {dep}")
                    return False

            try:
                # 更新狀態
                plugin_info.state = PluginState.LOADING
                self._plugin_info[plugin_info.plugin_id] = plugin_info

                # 動態導入
                plugin_path = os.path.dirname(plugin_info.entry_point)
                sys.path.insert(0, plugin_path)

                # 實例化插件
                module_name = os.path.splitext(
                    os.path.basename(plugin_info.entry_point)
                )[0]
                module = __import__(module_name)
                plugin_class = getattr(module, "Plugin")
                plugin = plugin_class()

                # 初始化
                context = PluginContext(self.launcher)
                if not await plugin.initialize(context):
                    raise RuntimeError("初始化失敗")

                # 註冊
                self._plugins[plugin_info.plugin_id] = plugin
                plugin_info.state = PluginState.LOADED
                plugin_info.load_time = datetime.now().isoformat()

                logger.info(f"插件已載入: {plugin_info.name}")
                return True

            except Exception as e:
                logger.error(f"載入插件失敗: {plugin_info.plugin_id} - {e}")
                plugin_info.state = PluginState.ERROR
                return False

    async def unload_plugin(self, plugin_id: str) -> bool:
        """
        卸載插件

        Args:
            plugin_id: 插件 ID

        Returns:
            是否成功
        """
        async with self._lock:
            if plugin_id not in self._plugins:
                logger.warning(f"插件未載入: {plugin_id}")
                return True

            plugin = self._plugins[plugin_id]
            info = self._plugin_info.get(plugin_id)

            try:
                # 停用
                await self.deactivate_plugin(plugin_id)

                # 清理
                plugin.cleanup()

                # 移除
                del self._plugins[plugin_id]
                if info:
                    info.state = PluginState.UNLOADED

                logger.info(f"插件已卸載: {plugin_id}")
                return True

            except Exception as e:
                logger.error(f"卸載插件失敗: {plugin_id} - {e}")
                return False

    async def activate_plugin(self, plugin_id: str) -> bool:
        """
        啟用插件

        Args:
            plugin_id: 插件 ID

        Returns:
            是否成功
        """
        if plugin_id not in self._plugins:
            logger.error(f"插件未載入: {plugin_id}")
            return False

        plugin = self._plugins[plugin_id]

        try:
            plugin.activate()

            info = self._plugin_info.get(plugin_id)
            if info:
                info.state = PluginState.ACTIVE

            logger.info(f"插件已啟用: {plugin_id}")
            return True

        except Exception as e:
            logger.error(f"啟用插件失敗: {plugin_id} - {e}")
            return False

    async def deactivate_plugin(self, plugin_id: str) -> bool:
        """
        停用插件

        Args:
            plugin_id: 插件 ID

        Returns:
            是否成功
        """
        if plugin_id not in self._plugins:
            return True

        plugin = self._plugins[plugin_id]

        try:
            plugin.deactivate()

            info = self._plugin_info.get(plugin_id)
            if info:
                info.state = PluginState.LOADED

            logger.info(f"插件已停用: {plugin_id}")
            return True

        except Exception as e:
            logger.error(f"停用插件失敗: {plugin_id} - {e}")
            return False

    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """取得插件"""
        return self._plugins.get(plugin_id)

    def get_loaded_plugins(self) -> List[PluginInfo]:
        """取得已載入插件"""
        return [
            info
            for info in self._plugin_info.values()
            if info.state in [PluginState.LOADED, PluginState.ACTIVE]
        ]

    def register_event_handler(self, event_type: str, handler: Callable):
        """註冊事件處理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def emit_event(self, event_type: str, data: Any):
        """發射事件"""
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"事件處理失敗: {event_type} - {e}")


# ============================================================
# 視窗管理器
# ============================================================


class WindowManager:
    """
    視窗管理器

    功能：
    - 視窗創建/管理
    - 浮動視窗支援
    - 多螢幕支援
    - Z-order 管理
    """

    def __init__(self, launcher: "DesktopLauncher"):
        self.launcher = launcher
        self._windows: Dict[str, WindowConfig] = {}
        self._active_window: Optional[str] = None
        self._window_handles: Dict[str, Any] = {}

    def create_window(self, config: WindowConfig) -> str:
        """
        創建視窗

        Args:
            config: 視窗配置

        Returns:
            視窗 ID
        """
        # 檢查數量限制
        if len(self._windows) >= self.launcher.config.max_windows:
            raise RuntimeError("已達最大視窗數")

        self._windows[config.window_id] = config
        logger.info(f"創建視窗: {config.window_id} - {config.title}")

        return config.window_id

    def close_window(self, window_id: str) -> bool:
        """
        關閉視窗

        Args:
            window_id: 視窗 ID

        Returns:
            是否成功
        """
        if window_id not in self._windows:
            logger.warning(f"視窗不存在: {window_id}")
            return False

        config = self._windows[window_id]

        # 清理資源
        if window_id in self._window_handles:
            del self._window_handles[window_id]

        del self._windows[window_id]

        # 更新 active
        if self._active_window == window_id:
            self._active_window = None

        logger.info(f"關閉視窗: {window_id}")
        return True

    def get_window(self, window_id: str) -> Optional[WindowConfig]:
        """取得視窗配置"""
        return self._windows.get(window_id)

    def get_all_windows(self) -> List[WindowConfig]:
        """取得所有視窗"""
        return list(self._windows.values())

    def set_active_window(self, window_id: str):
        """設定 active 視窗"""
        if window_id in self._windows:
            self._active_window = window_id

    def update_window(self, window_id: str, updates: Dict[str, Any]):
        """
        更新視窗

        Args:
            window_id: 視窗 ID
            updates: 更新內容
        """
        if window_id in self._windows:
            for key, value in updates.items():
                if hasattr(self._windows[window_id], key):
                    setattr(self._windows[window_id], key, value)

    def find_windows(
        self, window_type: Optional[WindowType] = None
    ) -> List[WindowConfig]:
        """查找視窗"""
        if window_type:
            return [w for w in self._windows.values() if w.window_type == window_type]
        return list(self._windows.values())


# ============================================================
# 系統匣管理器
# ============================================================


class TrayManager:
    """
    系統匣管理器

    功能：
    - 系統匣圖示
    - 右鍵選單
    - 提示訊息
    - 工具提示
    """

    def __init__(self, launcher: "DesktopLauncher"):
        self.launcher = launcher
        self._items: Dict[str, SystemTrayItem] = {}
        self._icon_path: Optional[str] = None
        self._tooltip: str = "桌面 AI 助手"
        self._visible: bool = False

    def set_icon(self, icon_path: str):
        """設定圖示"""
        self._icon_path = icon_path

    def set_tooltip(self, tooltip: str):
        """設定工具提示"""
        self._tooltip = tooltip

    def add_item(self, item: SystemTrayItem):
        """新增項目"""
        self._items[item.item_id] = item

    def remove_item(self, item_id: str) -> bool:
        """移除項目"""
        if item_id in self._items:
            del self._items[item_id]
            return True
        return False

    def get_items(self) -> List[SystemTrayItem]:
        """取得所有項目"""
        return list(self._items.values())

    def show(self):
        """顯示系統匣"""
        self._visible = True
        logger.info("系統匣已顯示")

    def hide(self):
        """隱藏系統匣"""
        self._visible = False
        logger.info("系統匣已隱藏")

    def is_visible(self) -> bool:
        """是否可見"""
        return self._visible


# ============================================================
# 桌面啟動器主類
# ============================================================


class DesktopLauncher:
    """
    桌面啟動器

    功能：
    - 統一入口點
    - 生命週期管理
    - 插件系統
    - 視窗管理
    - 系統匣整合
    - 持久化記憶整合

    使用範例：
        # 建立啟動器
        launcher = DesktopLauncher()

        # 配置
        config = LaunchConfig(
            mode=LaunchMode.TRAY,
            persistent_memory_enabled=True
        )

        # 初始化
        await launcher.initialize(config)

        # 啟動
        await launcher.launch()

        # 等待
        await launcher.wait_for_shutdown()
    """

    def __init__(self):
        # 組件
        self.config: Optional[LaunchConfig] = None
        self.memory_manager = None
        self.plugin_manager: Optional[PluginManager] = None
        self.window_manager: Optional[WindowManager] = None
        self.tray_manager: Optional[TrayManager] = None

        # 狀態
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._message_queue: Queue = Queue()
        self._workers: List[asyncio.Task] = []

    async def initialize(self, config: LaunchConfig):
        """
        初始化

        Args:
            config: 啟動配置
        """
        self.config = config

        # 日誌配置
        logging.getLogger().setLevel(
            logging.DEBUG if config.debug_mode else getattr(logging, config.log_level)
        )

        # 初始化記憶體管理器
        if config.persistent_memory_enabled:
            from . import create_memory_manager

            self.memory_manager = await create_memory_manager()

        # 初始化插件管理器
        self.plugin_manager = PluginManager(self)

        # 初始化視窗管理器
        self.window_manager = WindowManager(self)

        # 初始化系統匣
        self.tray_manager = TrayManager(self)

        # 設定預設系統匣項目
        self._setup_default_tray_items()

        logger.info("桌面啟動器初始化完成")

    def _setup_default_tray_items(self):
        """設定預設系統匣項目"""
        if not self.tray_manager:
            return

        # 主選單
        self.tray_manager.add_item(
            SystemTrayItem(
                item_id="show", label="顯示主視窗", action=self.show_main_window
            )
        )

        self.tray_manager.add_item(
            SystemTrayItem(item_id="separator_1", label="", separator=True)
        )

        # 快速操作
        self.tray_manager.add_item(
            SystemTrayItem(
                item_id="new_chat",
                label="新對話",
                action=lambda: asyncio.create_task(self.start_new_chat()),
            )
        )

        self.tray_manager.add_item(
            SystemTrayItem(
                item_id="restore",
                label="恢復工作",
                action=lambda: asyncio.create_task(self.restore_session()),
            )
        )

        self.tray_manager.add_item(
            SystemTrayItem(item_id="separator_2", label="", separator=True)
        )

        # 設定
        self.tray_manager.add_item(
            SystemTrayItem(item_id="settings", label="設定", action=self.open_settings)
        )

        self.tray_manager.add_item(
            SystemTrayItem(item_id="separator_3", label="", separator=True)
        )

        # 離開
        self.tray_manager.add_item(
            SystemTrayItem(item_id="quit", label="離開", action=self.shutdown)
        )

    async def load_plugins(self) -> int:
        """
        載入所有插件

        Returns:
            成功數量
        """
        if not self.plugin_manager:
            return 0

        # 發現插件
        plugins = await self.plugin_manager.discover_plugins(self.config.plugin_dirs)

        # 依賴排序
        sorted_plugins = self._sort_by_dependencies(plugins)

        # 載入
        loaded = 0
        for info in sorted_plugins:
            if await self.plugin_manager.load_plugin(info):
                await self.plugin_manager.activate_plugin(info.plugin_id)
                loaded += 1

        return loaded

    def _sort_by_dependencies(self, plugins: List[PluginInfo]) -> List[PluginInfo]:
        """依賴排序"""
        # 建立依賴圖
        graph = {p.plugin_id: set(p.dependencies) for p in plugins}

        # 拓撲排序
        sorted_ids = []
        visited = set()

        def visit(plugin_id: str):
            if plugin_id in visited:
                return
            visited.add(plugin_id)

            for dep in graph.get(plugin_id, []):
                if dep in graph:
                    visit(dep)

            sorted_ids.append(plugin_id)

        for plugin in plugins:
            visit(plugin.plugin_id)

        # 返回排序後的列表
        return [p for p in plugins if p.plugin_id in sorted_ids]

    async def launch(self):
        """啟動"""
        if self._running:
            logger.warning("已經在執行")
            return

        self._running = True

        # 根據模式啟動
        if self.config.mode == LaunchMode.TRAY:
            self.tray_manager.show()
            # 在背景執行
        elif self.config.mode == LaunchMode.MINIMIZED:
            # 最小化啟動
            pass
        elif self.config.mode == LaunchMode.BACKGROUND:
            # 背景執行
            pass
        else:
            # 正常啟動
            await self._create_main_window()

        # 自動恢復對話
        if self.config.auto_restore_session and self.memory_manager:
            await self._auto_restore()

        # 載入插件
        if self.plugin_manager:
            loaded = await self.load_plugins()
            logger.info(f"已載入 {loaded} 個插件")

        logger.info("桌面啟動器已啟動")

    async def _create_main_window(self):
        """創建主視窗"""
        config = WindowConfig(
            window_id="main",
            title="AI 助手",
            window_type=WindowType.MAIN,
            width=1000,
            height=700,
        )
        self.window_manager.create_window(config)

    async def _auto_restore(self):
        """自動恢復"""
        if not self.memory_manager:
            return

        # 恢復所有未完成會話
        from .state_restorer import StateRestorer

        restorer = StateRestorer(self.memory_manager.storage)
        result = restorer.restore_all_unfinished()

        if result.restored_items:
            logger.info(f"自動恢復了 {len(result.restored_items)} 個項目")

    async def start_new_chat(self):
        """開始新對話"""
        if not self.memory_manager:
            return

        session_id = await self.memory_manager.create_session("新對話")
        logger.info(f"創建新對話: {session_id}")

    async def restore_session(self):
        """恢復對話"""
        if not self.memory_manager:
            return

        active = self.memory_manager.get_active_sessions()
        if active:
            logger.info(f"恢復對話: {active[0]['session_id']}")

    def show_main_window(self):
        """顯示主視窗"""
        # 這裡實際會呼叫原生 API
        logger.info("顯示主視窗")

    def open_settings(self):
        """開啟設定"""
        config = WindowConfig(
            window_id="settings",
            title="設定",
            window_type=WindowType.SETTINGS,
            width=600,
            height=500,
        )
        self.window_manager.create_window(config)

    def emit_event(self, event_type: str, data: Any, source: Any = None):
        """發射事件"""
        if self.plugin_manager:
            asyncio.create_task(self.plugin_manager.emit_event(event_type, data))

    async def wait_for_shutdown(self):
        """等待關閉"""
        await self._shutdown_event.wait()

    def shutdown(self):
        """關閉"""
        if not self._running:
            return

        self._running = False

        # 停止所有 worker
        for worker in self._workers:
            worker.cancel()

        # 清理插件
        if self.plugin_manager:
            plugins = self.plugin_manager.get_loaded_plugins()
            for info in plugins:
                asyncio.create_task(self.plugin_manager.unload_plugin(info.plugin_id))

        # 關閉記憶體管理器
        if self.memory_manager:
            asyncio.create_task(self.memory_manager.close())

        # 隱藏系統匣
        if self.tray_manager:
            self.tray_manager.hide()

        # 關閉事件
        self._shutdown_event.set()

        logger.info("桌面啟動器已關閉")

    def get_status(self) -> Dict[str, Any]:
        """取得狀態"""
        return {
            "running": self._running,
            "windows": len(self._windows) if self.window_manager else 0,
            "plugins": len(self.plugin_manager.get_loaded_plugins())
            if self.plugin_manager
            else 0,
            "tray_visible": self.tray_manager.is_visible()
            if self.tray_manager
            else False,
            "mode": self.config.mode.value if self.config else None,
        }


# ============================================================
# 便捷函數
# ============================================================


async def create_launcher(
    mode: str = "normal",
    db_path: str = "data/persistent_memory.db",
    enable_persistence: bool = True,
) -> DesktopLauncher:
    """
    建立桌面啟動器的便捷函數

    Args:
        mode: 啟動模式
        db_path: 資料庫路徑
        enable_persistence: 啟用持久化

    Returns:
        DesktopLauncher
    """
    config = LaunchConfig(
        mode=LaunchMode(mode),
        persistent_memory_enabled=enable_persistence,
        workspace_path=os.getcwd(),
    )

    launcher = DesktopLauncher()
    await launcher.initialize(config)

    return launcher


# ============================================================
# 使用範例
# ============================================================


async def main():
    """使用範例"""
    # 建立啟動器
    launcher = await create_launcher(mode="tray", enable_persistence=True)

    # 啟動
    await launcher.launch()

    # 等待一段時間
    await asyncio.sleep(5)

    # 取得狀態
    status = launcher.get_status()
    print(f"狀態: {json.dumps(status, indent=2, ensure_ascii=False)}")

    # 關閉
    launcher.shutdown()

    await launcher.wait_for_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
