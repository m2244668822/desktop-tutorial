#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能體大腦儀表板 (Agent Brain Dashboard)
統一管理監控、優化與對話
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# 嘗試導入現有組件
try:
    from agent_monitor import AgentMonitor
    from agent_performance_booster import AgentPerformanceBoost
    from agent_coordinator import AgentCoordinator
except ImportError as e:
    print(f"⚠️  警告: 部分組件缺失 ({e})，建議先運行 agent_system_upgrader.py")

class AgentBrainDashboard:
    def __init__(self):
        self.monitor = AgentMonitor()
        self.booster = AgentPerformanceBoost()
        self.coordinator = AgentCoordinator()
        
    def start_background_services(self):
        print("🚀 啟動後台監控服務...")
        self.monitor.start_monitoring(interval=30)
        
    def run_pre_chat_optimization(self):
        print("⚡ 執行對話前性能優化...")
        self.booster.generate_performance_report()
        
    def launch_chat(self):
        print("\n💬 準備啟動對話系統...")
        chat_script = BASE_DIR / "start_chat_improved.sh"
        if chat_script.exists():
            try:
                # 使用 subprocess 啟動 shell 腳本
                subprocess.run(["bash", str(chat_script)], check=True)
            except KeyboardInterrupt:
                print("\n👋 對話已結束")
        else:
            print(f"❌ 找不到對話腳本: {chat_script}")

    def run(self):
        os.system('clear')
        print("="*60)
        print("  🧠 智能體系統大腦儀表板 v1.0")
        print("="*60)
        print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            self.start_background_services()
            self.run_pre_chat_optimization()
            
            print("\n" + "-"*40)
            print("系統狀態:")
            stats = self.monitor.get_current_stats()
            print(f"  • CPU 使用率: {stats.get('cpu', 'N/A')}%")
            print(f"  • 內存使用率: {stats.get('memory', 'N/A')}%")
            print("-"*40)
            
            self.launch_chat()
            
        finally:
            print("\n🛑 正在停止後台服務...")
            self.monitor.stop_monitoring()
            print("✅ 系統安全關閉")

if __name__ == "__main__":
    dashboard = AgentBrainDashboard()
    dashboard.run()
