#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接啟動前後端和網站
"""
import subprocess
import sys
import os
from pathlib import Path

BASE_DIR = Path(r"g:\城城城程式")
os.chdir(str(BASE_DIR))

print("\n" + "="*50)
print("  🚀 AI 智能體協作系統")
print("="*50)
print(f"\n📂 工作目錄: {BASE_DIR}")
print(f"🐍 Python: {sys.version.split()[0]}")
print(f"\n🌐 啟動 Web 模式...")
print(f"📍 訪問地址: http://127.0.0.1:5001")
print("\n" + "="*50 + "\n")

# 啟動系統
try:
    # 使用 subprocess 啟動，這樣可以獲得完整的日誌輸出
    result = subprocess.run(
        [sys.executable, "system_main.py", "web", "--open-browser", "--skip-health"],
        cwd=str(BASE_DIR)
    )
    sys.exit(result.returncode)
except KeyboardInterrupt:
    print("\n\n✅ 系統已停止")
    sys.exit(0)
except Exception as e:
    print(f"\n❌ 啟動失敗: {e}")
    sys.exit(1)
