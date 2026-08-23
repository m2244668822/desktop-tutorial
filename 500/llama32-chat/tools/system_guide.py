#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
程式組塊整理和起動指南
- 將相關程式模組組織在一起
- 提供統一的起動入口
- 集成異常通報系統
"""

import sys
from pathlib import Path
from datetime import datetime


class SystemStartup:
    """系統啟動和協調"""

    # 程式邏輯分組
    CORE_COMPONENTS = {
        "神經系統": {
            "files": ["neural_hub.py", "neural_chat.py"],
            "description": "核心神經網絡和決策系統",
            "dependencies": ["data/conversations.json"],
        },
        "中樞管理": {
            "files": ["central_hub.py", "chat_integration.py"],
            "description": "統一的中樞管理和接口",
            "dependencies": ["neural_hub.py"],
        },
        "智能體系統": {
            "files": ["agent.py", "autonomous_agent.py", "agent_communication.py"],
            "description": "智能體和自主決策",
            "dependencies": [],
        },
        "任務管理": {
            "files": ["task_manager.py", "task_monitor.py"],
            "description": "任務分配和監控",
            "dependencies": ["agent.py"],
        },
        "通信系統": {
            "files": ["traffic_controller.py", "code_updater_agent.py"],
            "description": "流量控制和代碼更新",
            "dependencies": ["agent.py"],
        },
        "自主監控": {
            "files": ["autonomous_monitor.py"],
            "description": "自動監控和異常通報",
            "dependencies": ["neural_hub.py", "agent.py"],
        },
        "輔助工具": {
            "files": ["utils.py", "constants.py", "monitor.py"],
            "description": "工具函數和配置",
            "dependencies": [],
        },
    }

    def __init__(self):
        self.base_dir = Path(".")
        self.status = {}

    def display_overview(self):
        """顯示系統概覽"""
        print("\n" + "=" * 70)
        print("🚀 神經系統和智能體 - 統一協調系統")
        print("=" * 70)

        print("\n📚 程式邏輯分組:")
        print("-" * 70)

        for group_name, group_info in self.CORE_COMPONENTS.items():
            print(f"\n🔹 {group_name}")
            print(f"   說明: {group_info['description']}")
            print(f"   文件:")
            for file in group_info["files"]:
                path = self.base_dir / file
                if path.exists():
                    size = path.stat().st_size / 1024  # KB
                    print(f"      ✓ {file} ({size:.1f} KB)")
                else:
                    print(f"      ✗ {file} (找不到)")

    def display_startup_guide(self):
        """顯示啟動指南"""
        print("\n" + "=" * 70)
        print("🎯 啟動指南")
        print("=" * 70)

        guide = """
1️⃣ 基本啟動 (最小化模式)
   python3 -c "from neural_chat import NeuralChat; chat = NeuralChat(); print('✅ 神經系統已就緒')"

2️⃣ 完整啟動 (包含監控)
   from neural_hub import NeuroHub
   from autonomous_monitor import AutonomousMonitor
   
   hub = NeuroHub()
   monitor = AutonomousMonitor()
   monitor.start()

3️⃣ 智能體模式
   from agent import agent
   from autonomous_agent import AutonomousAgent
   
   autonomous = AutonomousAgent()
   autonomous.start()

4️⃣ 完整系統 (所有組件同時運行)
   - 神經系統處理查詢
   - 智能體管理任務
   - 監控系統發現異常
   - 三者自主協作

---

🔗 組件間通信:

   查詢 →  神經系統 (NeuroHub)
            ↓
        異常檢測 → 異常通報系統
            ↓
        建議 → 智能體 (Agent)
            ↓
        執行 → 監控系統 (Monitor)
            ↓
        反饋 ← 自主決策
"""
        print(guide)

    def display_integration_map(self):
        """顯示整合地圖"""
        print("\n" + "=" * 70)
        print("🗺️ 系統整合地圖")
        print("=" * 70)

        map_text = """
文件結構:
├── 神經系統/
│   ├── neural_hub.py ✨ (核心)
│   ├── neural_chat.py 🗣️ (API)
│   └── central_hub.py 📊 (管理)
│
├── 智能體/
│   ├── agent.py 🤖 (核心)
│   ├── autonomous_agent.py 🔄 (自主)
│   └── agent_communication.py 💬 (通信)
│
├── 監控系統/
│   ├── autonomous_monitor.py 👁️ (監控)
│   ├── monitor.py 📈 (性能)
│   └── task_monitor.py ✅ (任務)
│
├── 任務管理/
│   ├── task_manager.py 📋 (管理)
│   └── task_monitor.py ✅ (監視)
│
├── 通信控制/
│   ├── traffic_controller.py 🚦 (流量)
│   └── agent_communication.py 💬 (通訊)
│
├── 工具庫/
│   ├── utils.py 🔧 (工具)
│   ├── constants.py ⚙️ (常數)
│   └── chat.py 💻 (聊天)
│
└── 文檔/ (已組織)
    ├── 快速開始/
    ├── 完整指南/
    ├── 架構設計/
    ├── 整合指南/
    ├── 項目完成/
    ├── 優化建議/
    └── OpenAI數據/

數據:
├── data/conversations.json (對話數據)
├── neural_anomalies.json (神經異常日誌)
├── agent_anomalies.json (智能體異常日誌)
└── monitor_logs.json (監控日誌)
"""
        print(map_text)

    def display_autonomous_features(self):
        """顯示自主工作特性"""
        print("\n" + "=" * 70)
        print("🤖 自主工作和異常通報")
        print("=" * 70)

        features = """
神經系統自主能力:
✅ 自動異常檢測 - 檢測到不確定查詢時通報
✅ 自動敏感度調整 - 根據置信度動態調整
✅ 自動邊界識別 - 發現超出領域的查詢
✅ 自動模型推薦 - 根據複雜度推薦最佳模型

智能體自主能力:
✅ 自動任務分配 - 根據負載自動分配任務
✅ 自動故障轉移 - 任務失敗時轉移給備用智能體
✅ 自動重啟機制 - 檢測到無響應時自動重啟
✅ 自動學習 - 從失敗中學習並改進

監控系統自主能力:
✅ 24/7 自動監控 - 持續監視系統狀態
✅ 實時異常通報 - 發現異常時立即通報
✅ 自動警報分級 - 根據嚴重性分級處理
✅ 自動日誌記錄 - 所有事件自動記錄

協作機制:
✅ 神經系統 ↔ 智能體 - 共享知識庫和決策結果
✅ 智能體 ↔ 監控系統 - 報告狀態和異常
✅ 監控系統 ↔ 神經系統 - 反饋性能和異常
✅ 三角自主協作 - 形成自我調節系統
"""
        print(features)


def main():
    startup = SystemStartup()

    startup.display_overview()
    startup.display_startup_guide()
    startup.display_integration_map()
    startup.display_autonomous_features()

    print("\n" + "=" * 70)
    print("✨ 系統已組織完成！")
    print("=" * 70)
    print("\n推薦下一步:")
    print("1. 查看 文檔/文檔索引.md 了解完整文檔")
    print("2. 運行 python3 autonomous_monitor.py 啟動監控")
    print("3. 使用 from neural_chat import NeuralChat 開始使用")
    print("\n🚀 準備就緒！\n")


if __name__ == "__main__":
    main()
