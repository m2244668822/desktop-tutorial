import time
import subprocess
import os
import json
from pathlib import Path

# 定義
USAGE_FILE = Path("config/api_usage.json")
MAX_DAILY_QUOTA = 1.0  # 根據 check_traffic.py 的進度條邏輯


def get_current_traffic():
    if not USAGE_FILE.exists():
        return 0.0
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            usage = json.load(f)
            return usage.get("today", 0.0)
    except:
        return 0.0


def log_event(msg):
    with open("marathon.log", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)


def run_step(name, cmd):
    log_event(f"🏃 啟動步驟: {name}")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        log_event(f"✅ 步驟完成: {name}")
    except Exception as e:
        log_event(f"❌ 步驟失敗 [{name}]: {e}")


def marathon():
    log_event("🚀 深度學習馬拉松正式啟動！全開放權限，直到流量耗盡。")

    round_count = 1
    while True:
        traffic = get_current_traffic()
        if traffic >= MAX_DAILY_QUOTA:
            log_event(f"🏁 流量已達標 ({traffic:.2f})，今日馬拉松圓滿結束。")
            break

        log_event(
            f"🔄 --- 第 {round_count} 輪深度學習開始 (當前流量: {traffic:.4f}) ---"
        )

        # 1. 抓取學術論文 (Researcher 任務)
        run_step("學術抓取", ["python3", "fetch_academic_daily.py"])

        # 2. 自我修復 (Engineer 任務)
        run_step("任務自癒", ["python3", "orca_self_heal.py"])

        # 3. 執行 CNS 神經成長 (Learner 任務)
        run_step(
            "神經成長",
            ["python3", "agent_self_learning_upgraded.py", "--mode", "quick_sync"],
        )

        # 4. 觸發索引更新 (系統維護)
        run_step(
            "索引同步", ["python3", "auto_pre_index.py", "--run-once"]
        )  # 修改 auto_pre_index 支持單次執行

        round_count += 1
        log_event("⏳ 進入冷卻期 5 分鐘，準備下一輪進攻...")
        time.sleep(300)


if __name__ == "__main__":
    marathon()
