#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系統單一主入口（Unified System Entrypoint）

目標：
1) 將目前分散的啟動流程聚合成單一程式入口
2) 保持既有 desktop_chat_app.py 能力不變（僅做調度）
3) 提供一致 CLI：
   - web     : 主線 Web 伺服器模式（預設）
   - desktop : pywebview 桌面模式
   - health  : 啟動前快速健康檢查
   - autopilot: 後台自治守護模式（定時巡檢 + 任務隊列自動執行）
"""

from __future__ import annotations

import argparse
import builtins
import os
import subprocess
import sys
from pathlib import Path

from core.data_paths import ProjectPaths


BASE_DIR = Path(__file__).resolve().parent
PATHS = ProjectPaths(BASE_DIR)


def _safe_print(*args, **kwargs):
    """Avoid Windows cp950 crashes when output includes unsupported chars."""
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        target_encoding = (getattr(sys.stdout, "encoding", None) or "utf-8").lower()
        fallback = " ".join(str(part) for part in args)
        fallback = fallback.encode(target_encoding, errors="ignore").decode(
            target_encoding, errors="ignore"
        )
        builtins.print(fallback)


print = _safe_print


def run(cmd: list[str]) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run(cmd, cwd=str(BASE_DIR), env=env, check=False)
    return int(proc.returncode or 0)


def _is_runnable_python(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        proc = subprocess.run(
            [str(path), "--version"],
            cwd=str(BASE_DIR),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return int(proc.returncode or 0) == 0
    except Exception:
        return False


def resolve_python_bin() -> Path | None:
    if sys.platform.startswith("win"):
        candidates = [
            BASE_DIR / ".venv" / "Scripts" / "python.exe",  # Windows
            BASE_DIR / ".venv" / "Scripts" / "python",  # Git Bash/WSL mixed setup
            BASE_DIR / ".venv" / "bin" / "python",  # fallback if copied from Unix
        ]
    else:
        candidates = [
            BASE_DIR / ".venv" / "bin" / "python",  # macOS / Linux
            BASE_DIR / ".venv" / "Scripts" / "python.exe",  # fallback if copied from Windows
            BASE_DIR / ".venv" / "Scripts" / "python",
        ]
    for candidate in candidates:
        if _is_runnable_python(candidate):
            return candidate
    current = Path(sys.executable).resolve()
    if _is_runnable_python(current):
        return current
    return None


def ensure_python() -> Path | None:
    python_bin = resolve_python_bin()
    if python_bin is None:
        print("❌ 找不到 .venv Python 執行檔")
        print("   已嘗試：.venv/bin/python、.venv/Scripts/python.exe")
        print("   請先建立虛擬環境，再執行 system_main.py")
    return python_bin


def health_check(python_bin: Path) -> int:
    print("🔍 執行系統健康檢查...")
    checker = PATHS.tools / "check_desktop_runtime.py"
    if checker.exists():
        return run([str(python_bin), str(checker)])
    print("⚠️ 未找到 tools/check_desktop_runtime.py，略過檢查")
    return 0


def _ensure_gpt_server(python_bin: Path):
    """確保 GPT 紀錄庫服務在背景運行"""
    server_script = BASE_DIR / ".tmp_chatgpt_server.py"
    if server_script.exists():
        # 簡單檢查是否已在運行 (透過埠號判斷或直接啟動，Popen 不會阻塞)
        try:
            if sys.platform.startswith("win"):
                # Windows 下使用 Popen 啟動，不顯示視窗
                subprocess.Popen(
                    [str(python_bin), str(server_script)],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                subprocess.Popen(
                    [str(python_bin), str(server_script)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            print("✅ 已確保 GPT 紀錄庫服務在背景運行")
        except Exception:
            pass

def launch_web(
    python_bin: Path, host: str, port: int, open_browser: bool, energy_lite: bool
) -> int:
    _ensure_gpt_server(python_bin)
    cmd = [
        str(python_bin),
        str(BASE_DIR / "desktop_chat_app.py"),
        "web",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if open_browser:
        cmd.append("--open-browser")
    if energy_lite:
        cmd.append("--energy-lite")
    print(f"🌐 啟動 Web 系統：{host}:{port}")
    return run(cmd)


def launch_desktop(python_bin: Path, energy_lite: bool, unified: bool) -> int:
    _ensure_gpt_server(python_bin)
    cmd = [str(python_bin), "desktop_chat_app.py", "desktop"]
    if energy_lite:
        cmd.append("--energy-lite")
    if unified:
        cmd.append("--unified")
    print("🖥️ 啟動桌面系統")
    return run(cmd)


def launch_autopilot(
    python_bin: Path, interval: int, skill_check_minutes: int, skip_health: bool
) -> int:
    if not skip_health:
        rc = health_check(python_bin)
        if rc != 0:
            print("❌ 健康檢查失敗，自治守護未啟動。")
            return rc
    daemon = PATHS.tools / "agent_autonomy_daemon.py"
    cmd = [
        str(python_bin),
        str(daemon),
        "--interval",
        str(interval),
        "--skill-check-minutes",
        str(skill_check_minutes),
    ]
    print(
        f"🤖 啟動自治守護模式 interval={interval}s skill_check={skill_check_minutes}min"
    )
    return run(cmd)


def display_banner():
    """顯示啟動標題"""
    print("\n" + "=" * 80)
    print()
    print("   ╔════════════════════════════════════════════════════════════════╗")
    print("   ║                                                                ║")
    print("   ║      🧠 智能體統一系統 v3.0 (Unified Entrypoint)            ║")
    print("   ║      Integrated AI Agent with Memory & Self-Learning          ║")
    print("   ║                                                                ║")
    print("   ║      ✨ 模式：Web | Desktop | Autopilot | Maintenance        ║")
    print("   ║      • 完整背景巡查與主動巡查快照注入                        ║")
    print("   ║      • 多空間隔離與長期記憶 L0/L1/L2 分層                    ║")
    print("   ║                                                                ║")
    print("   ╚════════════════════════════════════════════════════════════════╝")
    print()
    print("=" * 80)
    print()


def display_interactive_menu():
    """顯示交互式菜單"""
    print("請選擇功能：\n")
    print("  1️⃣   啟動 Web 伺服器 (預設模式)")
    print("  2️⃣   啟動 桌面應用程式")
    print("  3️⃣   啟動 自治守護模式 (Autopilot)")
    print("  4️⃣   執行 系統健康檢查 (Health Check)")
    print("  ------------------------------------------")
    print("  5️⃣   查看 學習統計面板 (Learning Dashboard)")
    print("  6️⃣   查看 用戶檔案分析 (Memory Profile)")
    print("  7️⃣   執行 診斷記憶系統 (Diagnose Memory)")
    print("  8️⃣   執行 深度自主學習 (Self-Learning)")
    print("  9️⃣   重建 知識中樞索引 (Rebuild Hub - 包含 GPT 紀錄庫)")
    print("  🔟   啟動 GPT 紀錄庫服務 (GPT History Server)")
    print("  0️⃣   退出\n")

    choice = input("  📍 請輸入選項 (0-10): ").strip()
    return choice


def run_interactive_menu(python_bin: Path, args: argparse.Namespace) -> int:
    display_banner()
    while True:
        choice = display_interactive_menu()
        if choice == "1":
            return launch_web(python_bin, args.host, args.port, True, args.energy_lite)
        elif choice == "2":
            return launch_desktop(python_bin, args.energy_lite, args.unified)
        elif choice == "3":
            return launch_autopilot(python_bin, args.autopilot_interval, args.autopilot_skill_check_minutes, args.skip_health)
        elif choice == "4":
            health_check(python_bin)
        elif choice == "5":
            run([str(python_bin), str(BASE_DIR / "view_learning_dashboard.py")])
        elif choice == "6":
            run([str(python_bin), str(BASE_DIR / "view_memory_profile.py")])
        elif choice == "7":
            run([str(python_bin), str(BASE_DIR / "diagnose_memory.py")])
        elif choice == "8":
            run([str(python_bin), str(BASE_DIR / "agent_self_learning_upgraded.py")])
        elif choice == "9":
            print("\n🚀 正在重建知識中樞索引...")
            # 直接調用 KnowledgeHub rebuild
            cmd = f"from core.knowledge_hub import KnowledgeHub; hub=KnowledgeHub('{BASE_DIR}'); print(hub.rebuild())"
            run([str(python_bin), "-c", cmd])
        elif choice == "10":
            print("\n🚀 啟動 GPT 紀錄庫服務 (背景)...")
            server_script = BASE_DIR / ".tmp_chatgpt_server.py"
            if server_script.exists():
                # 使用 start 命令在 Windows 背景啟動，或直接 run
                if sys.platform.startswith("win"):
                    subprocess.Popen(["start", "python", str(server_script)], shell=True)
                else:
                    subprocess.Popen([str(python_bin), str(server_script)])
                print("✅ 服務已在背景啟動 (預設埠 5000)")
            else:
                print("❌ 找不到 .tmp_chatgpt_server.py")
        elif choice == "0":
            print("\n👋 再見！")
            return 0
        else:
            print("\n❌ 無效選項，請重試")
        
        input("\n按 Enter 返回菜單...")
        print("\n" + "=" * 80 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI 智能體中心：系統單一主入口")
    parser.add_argument(
        "mode",
        nargs="?",
        default="menu",
        choices=["web", "desktop", "health", "autopilot", "menu"],
        help="啟動模式（預設 menu）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Web 主機位址")
    parser.add_argument("--port", type=int, default=5001, help="Web 連接埠")
    parser.add_argument(
        "--open-browser", action="store_true", help="Web 模式啟動後自動開瀏覽器"
    )
    parser.add_argument(
        "--energy-lite", action="store_true", help="節能模式（降低輪詢與負載）"
    )
    parser.add_argument(
        "--unified", action="store_true", help="桌面模式使用單視窗（傳統 unified 頁面）"
    )
    parser.add_argument(
        "--skip-health", action="store_true", help="略過啟動前健康檢查"
    )
    parser.add_argument(
        "--autopilot-interval",
        type=int,
        default=30,
        help="autopilot 迴圈間隔秒數（最小 5）",
    )
    parser.add_argument(
        "--autopilot-skill-check-minutes",
        type=int,
        default=10,
        help="autopilot skill 穩定性巡檢頻率（分鐘）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    python_bin = ensure_python()
    if python_bin is None:
        return 1

    if args.mode == "menu":
        return run_interactive_menu(python_bin, args)

    if args.mode == "health":
        return health_check(python_bin)

    if not args.skip_health:
        rc = health_check(python_bin)
        if rc != 0:
            print("❌ 健康檢查失敗，已停止啟動。")
            return rc

    if args.mode == "web":
        return launch_web(
            python_bin=python_bin,
            host=args.host,
            port=args.port,
            open_browser=bool(args.open_browser),
            energy_lite=bool(args.energy_lite),
        )

    if args.mode == "autopilot":
        return launch_autopilot(
            python_bin=python_bin,
            interval=max(5, int(args.autopilot_interval)),
            skill_check_minutes=max(1, int(args.autopilot_skill_check_minutes)),
            skip_health=bool(args.skip_health),
        )

    return launch_desktop(
        python_bin=python_bin,
        energy_lite=bool(args.energy_lite),
        unified=bool(args.unified),
    )


if __name__ == "__main__":
    sys.exit(main())

