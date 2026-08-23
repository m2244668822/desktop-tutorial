#!/usr/bin/env python3
import json
import os
from pathlib import Path
from datetime import datetime


def check_traffic():
    usage_file = Path("config/api_usage.json")
    config_file = Path("config/gemini_config.json")

    # 讀取當前模型
    model_name = "未知模型"
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
            model_name = config.get("model", "gemini-1.5-flash")

    print("\n" + "=" * 40)
    print(f" 📊 流量消耗監控 (模型: {model_name})")
    print("=" * 40)

    if not usage_file.exists():
        print("目前尚無流量統計數據。")
        return

    with open(usage_file, "r", encoding="utf-8") as f:
        usage = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    last_reset = usage.get("last_reset", "未知")

    print(f" 📅 今日日期: {today}")
    print(f" 🔄 最後重置: {last_reset}")
    print("-" * 40)
    print(f" 📈 今日消耗: {usage.get('today', 0):.4f} 單位")
    print(f" 📜 累計消耗: {usage.get('total', 0):.4f} 單位")

    # 簡易進度條 (假設 1.0 是某個限制或目標)
    percent = min(usage.get("today", 0) * 100, 100)
    bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
    print(f" ⚡ 今日使用進度: [{bar}] {percent:.1f}%")

    print("=" * 40)
    print(" 💡 提示: 使用 gemini-1.5-flash 可以更有效地節省流量。")
    print("=" * 40 + "\n")


if __name__ == "__main__":
    check_traffic()
