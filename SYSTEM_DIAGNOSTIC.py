#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系統診斷工具 - 完整系統健康檢查
System Diagnostic Tool - Complete System Health Check
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import time

BASE_DIR = Path(__file__).resolve().parent


def run_command(cmd):
    """執行命令並返回結果"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except Exception as e:
        return f"ERROR: {e}", -1


def check_ollama_process():
    """檢查 Ollama 進程"""
    print("\n【1. Ollama 進程檢查】")
    output, code = run_command("ps aux | grep ollama | grep serve | grep -v grep")

    if code == 0 and output:
        print(f"  ✅ Ollama 運行中")
        print(f"     {output}")
        # 提取 PID
        pid = output.split()[1]
        return True, pid
    else:
        print(f"  ❌ Ollama 未運行")
        return False, None


def check_ollama_api():
    """檢查 Ollama API"""
    print("\n【2. Ollama API 檢查】")
    output, code = run_command("curl -s http://localhost:11434/api/tags --max-time 3")

    if code == 0 and output:
        try:
            data = json.loads(output)
            models = [m["name"] for m in data.get("models", [])]
            if models:
                print(f"  ✅ Ollama API 正常")
                print(f"     可用模型: {', '.join(models)}")
                return True, models
            else:
                print(f"  ⚠️ Ollama API 正常但無模型")
                return False, []
        except json.JSONDecodeError:
            print(f"  ❌ Ollama API 返回無效 JSON")
            return False, []
    else:
        print(f"  ❌ Ollama API 無法訪問")
        return False, []


def check_system_memory():
    """檢查系統內存；避免用單一 unused MB 快照誤判。"""
    print("\n【3. 系統內存檢查】")
    pressure, pressure_code = run_command("memory_pressure -Q")
    swap, _ = run_command("sysctl vm.swapusage")
    top_line, _ = run_command("top -l 1 | grep PhysMem")
    if top_line:
        print(f"  ℹ️ {top_line}")
    if swap:
        print(f"  ℹ️ {swap}")
    if pressure_code == 0 and pressure:
        match = re.search(r"System-wide memory free percentage:\\s*(\\d+)%", pressure)
        if match:
            free_percent = int(match.group(1))
            print(f"  ✅ 系統可用記憶體比例: {free_percent}%")
            if free_percent >= 15:
                print("     狀態: 可運作；大型索引重建仍建議使用背景批次")
                return True
            print("     警告: 記憶體壓力偏高，請暫停大型 JSON 與 FAISS 重建")
            return False
    print("  ⚠️ 無法讀取 memory_pressure，降級採用即時快照")
    if top_line and "unused" in top_line:
        return True
    return False


def check_knowledge_base():
    """檢查知識庫文件"""
    print("\n【4. 知識庫文件檢查】")
    base_path = BASE_DIR / "500" / "llama32-chat" / "data" / "local_knowledge"

    required_files = [
        "complete_chatgpt_database.json",
        "local_knowledge_base.json",
        "rag_index.json",
    ]

    all_exist = True
    for file_name in required_files:
        file_path = base_path / file_name
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            print(f"  ✅ {file_name} ({size_mb:.1f}MB)")
        else:
            print(f"  ❌ {file_name} 不存在")
            all_exist = False

    return all_exist


def check_chat_system():
    """檢查目前主線；舊離線腳本僅作 legacy 參考，不再視為必要檔。"""
    print("\n【5. 聊天系統文件檢查】")
    required_files = [
        BASE_DIR / "system_main.py",
        BASE_DIR / "desktop_chat_app.py",
        BASE_DIR / "core" / "web_server.py",
        BASE_DIR / "core" / "knowledge_hub.py",
    ]

    all_exist = True
    for file_path in required_files:
        if file_path.exists():
            print(f"  ✅ {file_path.relative_to(BASE_DIR)}")
        else:
            print(f"  ❌ {file_path.relative_to(BASE_DIR)} 不存在")
            all_exist = False
    print("  ℹ️ 舊 offline_local_chat*.py 已退出正式主線，不再作為啟動必要條件")

    return all_exist


def print_summary(results):
    """打印診斷摘要"""
    print("\n" + "=" * 60)
    print("【診斷結果摘要】")
    print("=" * 60)

    all_good = all(results.values())

    for check_name, is_ok in results.items():
        status = "✅ 正常" if is_ok else "❌ 異常"
        print(f"{check_name}: {status}")

    print("=" * 60)

    if all_good:
        print("\n🟢 系統完全就緒！")
        print("\n下一步: 運行以下命令啟動聊天系統")
        print(f"   cd {BASE_DIR}")
        print("   python3 system_main.py web --host 127.0.0.1 --port 5001 --energy-lite")
    else:
        print("\n🔴 系統存在問題，請檢查上方的詳細報告")

    print("\n")


def main():
    print("\n" + "=" * 60)
    print("系統診斷工具 - 啟動")
    print("=" * 60)
    print(f"診斷時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        "Ollama 進程": check_ollama_process()[0],
        "Ollama API": check_ollama_api()[0],
        "系統內存": check_system_memory(),
        "知識庫文件": check_knowledge_base(),
        "聊天系統文件": check_chat_system(),
    }

    print_summary(results)


if __name__ == "__main__":
    main()
