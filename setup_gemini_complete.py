#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemini + 本地記憶系統 - 完整設置指南
Gemini + Local Memory System - Complete Setup Guide
"""

import sys
import os
import json
from pathlib import Path

BASE_DIR = Path("/Volumes/智能體/城城城程式")


def print_banner():
    """打印標題"""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║   🧠 Gemini + 本地記憶統一對話系統                                        ║
║   Unified Chat with Gemini & All Local Memories                          ║
║                                                                            ║
║   包含: ChatGPT 數據庫 + 所有系統對話 + 知識庫                            ║
║   Includes: ChatGPT Database + All System Conversations + Knowledge Base  ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
""")


def check_api_key() -> str:
    """檢查和獲取 API 密鑰"""
    print("🔍 檢查 Gemini API 密鑰...\n")

    # 1. 環境變數
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        print("✅ 已找到環境變數 GEMINI_API_KEY")
        print(f"   前 20 字符: {api_key[:20]}...\n")
        return api_key

    # 2. 配置文件
    config_file = BASE_DIR / "config" / "gemini_config.json"
    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                config = json.load(f)
                api_key = config.get("api_key")
                if api_key and api_key != "GEMINI_API_KEY_PLACEHOLDER":
                    print("✅ 已找到本地配置文件")
                    print(f"   前 20 字符: {api_key[:20]}...\n")
                    return api_key
        except:
            pass

    return None


def show_setup_menu():
    """顯示設置菜單"""
    print("\n" + "=" * 80)
    print("  🔧 設置選項")
    print("=" * 80)
    print("""
  1️⃣  快速設置 - 交互式配置 API 密鑰
  2️⃣  環境變數 - 查看如何設置環境變數
  3️⃣  配置文件 - 查看如何使用配置文件
  4️⃣  驗證設置 - 檢查當前配置是否正常
  5️⃣  啟動對話 - 開始使用 Gemini 對話
  0️⃣  退出
""")

    choice = input("請選擇 (0-5): ").strip()
    return choice


def setup_interactive():
    """交互式設置"""
    print("\n" + "=" * 80)
    print("  互動式設置 Gemini API 密鑰")
    print("=" * 80)

    print("""
📍 獲取免費 API 密鑰:
   1. 訪問: https://aistudio.google.com/apikey
   2. 登入您的 Google 帳號
   3. 點擊 'Create API Key'
   4. 複製生成的密鑰並粘貼到下面

⚠️  注意: API 密鑰應保密，不要分享或上傳到公開倉庫
""")

    api_key = input("請輸入 API 密鑰: ").strip()

    if not api_key:
        print("❌ 密鑰不能為空")
        return False

    # 選擇保存方式
    print("\n💾 選擇保存方式:")
    print("   1) 環境變數 (推薦 - 更安全)")
    print("   2) 本地配置文件")
    print("   3) 兩者都保存")

    save_choice = input("請選擇 (1-3): ").strip()

    if save_choice in ["1", "3"]:
        os.environ["GEMINI_API_KEY"] = api_key
        print("✅ 已設置到環境變數")

    if save_choice in ["2", "3"]:
        config_file = BASE_DIR / "config" / "gemini_config.json"
        config = {
            "api_key": api_key,
            "model": "gemini-2.0-flash",
            "note": "此文件包含敏感信息，請勿分享",
        }
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.chmod(config_file, 0o600)
        print(f"✅ 已保存到配置文件: {config_file}")

    print("\n✅ API 密鑰設置成功！")
    return True


def show_env_setup():
    """顯示環境變數設置指南"""
    print("\n" + "=" * 80)
    print("  環境變數設置指南")
    print("=" * 80)
    print("""
方法 1️⃣  - 臨時設置 (當前終端有效):
----
   export GEMINI_API_KEY='your-api-key-here'

方法 2️⃣  - 永久設置 (推薦):
----
   # 針對 zsh (macOS 默認):
   echo "export GEMINI_API_KEY='your-api-key-here'" >> ~/.zshrc
   source ~/.zshrc
   
   # 或針對 bash:
   echo "export GEMINI_API_KEY='your-api-key-here'" >> ~/.bash_profile
   source ~/.bash_profile

驗證設置:
----
   echo $GEMINI_API_KEY

如果顯示您的 API 密鑰，則表示設置成功！
""")


def show_config_setup():
    """顯示配置文件設置指南"""
    config_file = BASE_DIR / "config" / "gemini_config.json"
    print("\n" + "=" * 80)
    print("  配置文件設置指南")
    print("=" * 80)
    print(f"""
配置文件位置: {config_file}

設置步驟:
1️⃣  建立/編輯配置文件:
   cat > {config_file} << 'EOF'
   {{
       "api_key": "your-api-key-here",
       "model": "gemini-2.0-flash"
   }}
   EOF

2️⃣  設置文件權限 (安全):
   chmod 600 {config_file}

3️⃣  驗證設置:
   python3 -c "import json; print(json.load(open('{config_file}')))"

⚠️  安全提示:
   • 不要將此文件提交到 Git
   • 確保文件權限為 600 (只有所有者可讀)
   • 不要在終端歷史中暴露 API 密鑰
""")


def verify_setup():
    """驗證設置"""
    print("\n" + "=" * 80)
    print("  驗證設置")
    print("=" * 80)
    print()

    # 檢查 Python 依賴
    try:
        import google.generativeai

        print("✅ google-generativeai 已安裝")
    except ImportError:
        print("❌ google-generativeai 未安裝")
        print("   請執行: pip install google-generativeai")
        return False

    # 檢查 API 密鑰
    api_key = check_api_key()
    if not api_key:
        print("❌ 未找到 API 密鑰")
        return False

    # 檢查本地記憶 API
    try:
        sys.path.insert(0, str(BASE_DIR / "tools"))
        from local_memory_api import LocalMemoryAPI

        memory_api = LocalMemoryAPI(str(BASE_DIR))
        print("✅ 本地記憶 API 正常")
        print(f"   • 數據源: 13 個")
        print(f"   • 包括: ChatGPT 數據庫 + 所有系統對話記錄")
    except Exception as e:
        print(f"⚠️  本地記憶 API 問題: {e}")

    print("\n✅ 所有設置驗證完成！")
    return True


def start_chat():
    """啟動對話"""
    print("\n" + "=" * 80)
    print("  🚀 啟動 Gemini + 本地記憶對話系統")
    print("=" * 80)
    print()

    # 檢查設置
    if not check_api_key():
        print("❌ API 密鑰未設置")
        print("   請先執行設置步驟")
        return False

    # 啟動對話系統
    script = BASE_DIR / "start_gemini_memory_chat.py"
    if script.exists():
        os.system(f"python3 {script}")
        return True
    else:
        print(f"❌ 對話腳本未找到: {script}")
        return False


def main():
    """主程序"""
    print_banner()

    while True:
        choice = show_setup_menu()

        if choice == "1":
            setup_interactive()
        elif choice == "2":
            show_env_setup()
        elif choice == "3":
            show_config_setup()
        elif choice == "4":
            verify_setup()
        elif choice == "5":
            start_chat()
        elif choice == "0":
            print("\n👋 再見！")
            break
        else:
            print("❌ 無效選擇")


if __name__ == "__main__":
    main()
