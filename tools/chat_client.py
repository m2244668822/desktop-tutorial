#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 智能體終端機介面 — 互動式 CLI
用法：python3 tools/chat_tui.py [agent]
可用智能體：dispatcher / researcher / engineer / xiaobian / whitehat / learner / general
"""

import sys
import json
import requests
import os
import textwrap

SERVER = os.getenv("CHAT_SERVER_URL", "http://127.0.0.1:5001")

AGENTS = {
    "d": "dispatcher",
    "dispatcher": "dispatcher",
    "r": "researcher",
    "researcher": "researcher",
    "e": "engineer",
    "engineer": "engineer",
    "x": "xiaobian",
    "xiaobian": "xiaobian",
    "w": "whitehat",
    "whitehat": "whitehat",
    "l": "learner",
    "learner": "learner",
    "g": "general",
    "general": "general",
}

AGENT_LABELS = {
    "dispatcher": "👑 總管",
    "researcher": "🔬 研究員",
    "engineer": "⚙️  工程師",
    "xiaobian": "✍️  小編",
    "whitehat": "🕵️  帽子",
    "learner": "🧠 學習者",
    "general": "🤖 通用",
}

# ── ANSI 顏色 ────────────────────────────────────
C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MUTED = "\033[2m"
C_BOLD = "\033[1m"


def c(text, color):
    return f"{color}{text}{C_RESET}"


def print_header(agent):
    label = AGENT_LABELS.get(agent, agent)
    print()
    print(c("╔══════════════════════════════════════╗", C_CYAN))
    print(c(f"║  AI 智能體終端機  ·  {label:<16}║", C_CYAN))
    print(c("╚══════════════════════════════════════╝", C_RESET))
    print(c(f"  伺服器：{SERVER}", C_MUTED))
    print(c("  指令：:agent <名稱>  :tasks  :status  :quit", C_MUTED))
    print()


def wrap_reply(text, width=72):
    lines = text.split("\n")
    out = []
    for line in lines:
        if len(line) <= width:
            out.append(line)
        else:
            out.extend(textwrap.wrap(line, width=width))
    return "\n".join(out)


def send_chat(message, agent, history):
    payload = {
        "message": message,
        "agent": agent,
        "model": "auto",
        "conversation": history[-12:],
    }
    try:
        r = requests.post(
            f"{SERVER}/chat/agent",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=90,
        )
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}: {r.text[:120]}"}
    except requests.exceptions.ConnectionError:
        return {"error": f"無法連線到 {SERVER}，請確認後端已啟動"}
    except requests.exceptions.Timeout:
        return {"error": "請求逾時（90s），模型可能正在載入"}
    except Exception as e:
        return {"error": str(e)}


def fetch_tasks():
    try:
        r = requests.get(f"{SERVER}/agent/tasks/summary", timeout=10)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def fetch_status():
    try:
        r = requests.get(f"{SERVER}/api/orchestrator/status", timeout=10)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def print_tasks(data):
    sc = data.get("status_counts", {})
    print()
    print(c("  📋 任務看板", C_BOLD))
    print(
        c(
            f"  待執行：{sc.get('pending', 0)}  執行中：{sc.get('running', 0)}  "
            f"已完成：{sc.get('completed', 0)}  失敗：{sc.get('failed', 0)}",
            C_MUTED,
        )
    )
    items = data.get("unresolved_items", [])
    if items:
        print()
        for t in items[:8]:
            st = t.get("status", "?")
            dot = {"pending": "🟡", "running": "🔵", "failed": "🔴"}.get(st, "⚪")
            title = (t.get("title") or "")[:50]
            agent = t.get("assigned_agent", "?")
            print(f"  {dot} [{agent:>10}]  {title}")
    print()


def print_status(data):
    print()
    print(c("  🔧 系統狀態", C_BOLD))
    print(f"  KAL 迴圈：{'運行中' if data.get('running') else '停止'}")
    print(f"  執行輪次：{data.get('cycle_count', 0)}")
    print(f"  待處理目標：{data.get('pending_goals', 0)}")
    kal = data.get("kal_loop", {})
    print(
        f"  蒸餾器：{'✅' if kal.get('distiller_active') else '❌'}  "
        f"驗證器：{'✅' if kal.get('validator_active') else '❌'}  "
        f"Brave：{'✅' if kal.get('brave_api') else '❌'}"
    )
    print()


def main():
    agent_arg = sys.argv[1].lower() if len(sys.argv) > 1 else "general"
    current_agent = AGENTS.get(agent_arg, "general")
    history = []

    print_header(current_agent)

    # 確認伺服器連線
    try:
        requests.get(f"{SERVER}/", timeout=3)
        print(c("  ✅ 後端已連線", C_GREEN))
    except Exception:
        print(c(f"  ⚠️  無法連線到 {SERVER}", C_YELLOW))
        print(c("     請先啟動後端：python3 chatgpt_server.py", C_MUTED))
    print()

    while True:
        label = AGENT_LABELS.get(current_agent, current_agent)
        try:
            user_input = input(c(f"[{label}] 你：", C_BLUE)).strip()
        except (EOFError, KeyboardInterrupt):
            print(c("\n\n  👋 再見！", C_CYAN))
            sys.exit(0)

        if not user_input:
            continue

        # ── 內建指令 ─────────────────────────────
        if user_input.startswith(":"):
            cmd = user_input[1:].strip().lower().split()
            if not cmd:
                continue
            if cmd[0] == "quit" or cmd[0] == "exit" or cmd[0] == "q":
                print(c("  👋 再見！", C_CYAN))
                sys.exit(0)
            elif cmd[0] == "agent" and len(cmd) > 1:
                new_agent = AGENTS.get(cmd[1])
                if new_agent:
                    current_agent = new_agent
                    history = []
                    print(c(f"  ✅ 切換到 {AGENT_LABELS.get(current_agent)}", C_GREEN))
                else:
                    keys = list(AGENTS.keys())
                    print(c(f"  ❌ 未知智能體，可用：{keys}", C_YELLOW))
            elif cmd[0] == "tasks":
                data = fetch_tasks()
                if data:
                    print_tasks(data)
                else:
                    print(c("  無法取得任務資料", C_YELLOW))
            elif cmd[0] == "status":
                data = fetch_status()
                if data:
                    print_status(data)
                else:
                    print(c("  無法取得狀態資料", C_YELLOW))
            elif cmd[0] == "clear":
                history = []
                print(c("  🧹 對話記憶已清除", C_MUTED))
            elif cmd[0] == "help":
                print(
                    c(
                        """
  指令列表：
    :agent <名稱>  切換智能體 (d/r/e/x/w/l/g)
    :tasks         顯示任務看板
    :status        顯示系統狀態
    :clear         清除對話記憶
    :quit          離開
""",
                        C_MUTED,
                    )
                )
            else:
                print(c(f"  未知指令：{user_input}", C_YELLOW))
            continue

        # ── 送出訊息 ─────────────────────────────
        print(c("  ⏳ 思考中...", C_MUTED), end="\r")
        result = send_chat(user_input, current_agent, history)

        if "error" in result:
            print(c(f"  ❌ {result['error']}", C_YELLOW))
            continue

        reply = result.get("response") or result.get("reply") or "（無回覆）"
        model = result.get("model", "?")
        rt = result.get("response_time", "")
        rt_str = f"  {rt:.1f}s" if isinstance(rt, (int, float)) else ""

        print(f"\r  {' ' * 30}\r", end="")  # 清除等待提示
        print(c(f"[{AGENT_LABELS.get(current_agent)}] AI：", C_GREEN))
        print()
        for line in wrap_reply(reply).split("\n"):
            print(f"  {line}")
        print()
        print(c(f"  ─ {model}{rt_str}", C_MUTED))
        print()

        history.append({"role": "user", "text": user_input})
        history.append({"role": "assistant", "text": reply})


if __name__ == "__main__":
    main()
