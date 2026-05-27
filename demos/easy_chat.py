#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
即時聊天工具 - 無緩存問題
使用方法：
1. 編輯 message.txt 文件
2. 執行: python easy_chat.py
"""

import sys
import os
from pathlib import Path

# 加入路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "500", "llama32-chat"))


def main():
    # 讀取訊息
    msg_file = Path("message.txt")

    if not msg_file.exists():
        print("❌ 請先創建 message.txt 文件並輸入你的訊息！")
        return

    with open(msg_file, "r", encoding="utf-8") as f:
        message = f.read().strip()

    if not message:
        print("❌ message.txt 是空的！請輸入訊息。")
        return

    print(f"📤 訊息: {message}\n")
    print("🤖 Gemini 回覆:\n")

    try:
        from chat import _call_gemini

        response = _call_gemini(message)
        print(f"\n\n✅ 完成！")
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")


if __name__ == "__main__":
    main()
