#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系統診斷工具 - 完整系統健康檢查
System Diagnostic Tool - Complete System Health Check
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import time


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
    """檢查系統內存"""
    print("\n【3. 系統內存檢查】")
    output, code = run_command("top -l 1 | grep PhysMem")

    if code == 0 and output:
        print(f"  ✅ {output}")
        # 提取無使用內存
        if "unused" in output:
            unused = output.split("unused")[0].split()[-1]
            unused_mb = int(unused.rstrip("M"))
            if unused_mb > 100:
                print(f"     狀態: 內存充足")
                return True
            else:
                print(f"     警告: 內存不足 ({unused_mb}MB)")
                return False
    return False


def check_knowledge_base():
    """檢查知識庫文件"""
    print("\n【4. 知識庫文件檢查】")
    base_path = Path("/Volumes/智能體/城城城程式/500/llama32-chat/data/local_knowledge")

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
    """檢查聊天系統文件"""
    print("\n【5. 聊天系統文件檢查】")
    base_path = Path("/Volumes/智能體/城城城程式/500/llama32-chat")

    required_files = ["offline_local_chat.py", "offline_local_chat_fixed.py"]

    all_exist = True
    for file_name in required_files:
        file_path = base_path / file_name
        if file_path.exists():
            print(f"  ✅ {file_name}")
        else:
            print(f"  ❌ {file_name} 不存在")
            all_exist = False

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
        print("\n下一步: 運行以下命令启動聊天系統")
        print("   cd /Volumes/智能體/城城城程式/500/llama32-chat")
        print("   python3 offline_local_chat.py")
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
