#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 設定路徑
BASE_DIR = Path(__file__).parent.parent.parent.parent
USAGE_FILE = BASE_DIR / "config/api_usage.json"
CONFIG_FILE = BASE_DIR / "config/gemini_config.json"

def load_json(path):
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def monitor():
    usage = load_json(USAGE_FILE)
    config = load_json(CONFIG_FILE)
    
    current_model = config.get('model', 'gemini-1.5-flash')
    today_usage = usage.get('today', 0)
    
    # 讀取預算策略 (這裡簡單示範，稍後可從 reference 讀取)
    THRESHOLD_WARNING = 0.05  # 消耗超過 0.05 單位時警告
    THRESHOLD_SWITCH = 0.08   # 消耗超過 0.08 單位時建議切換
    
    print(f"--- 流量監控報告 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ---")
    print(f"當前模型: {current_model}")
    print(f"今日消耗: {today_usage:.4f} 單位")
    
    if today_usage >= THRESHOLD_SWITCH and "2.0-flash" in current_model:
        print("\n⚠️  [緊急建議] 今日消耗已接近限制！")
        print("💡 建議切換至更經濟的模型: gemini-1.5-flash")
        print("指令範例: gemini config set model gemini-1.5-flash")
    elif today_usage >= THRESHOLD_WARNING:
        print("\n🔔 [提醒] 今日流量消耗較高，請注意。")
    else:
        print("\n✅ 流量處於安全範圍。")

if __name__ == "__main__":
    monitor()
