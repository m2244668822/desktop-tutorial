#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
連續自主學習引擎
- 讓智能體持續與語言模型對話學習
- 每輪自動提取重點、記錄反思
- 支援固定輪數或持續模式（直到 Ctrl+C）
"""

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from start_gemini_memory_chat import GeminiMemoryChat


# 全局標誌用於優雅關閉
shutdown_requested = False


def signal_handler(signum, frame):
    """處理中斷信號（SIGINT, SIGTERM）"""
    global shutdown_requested
    print(f"\n\n🛑 收到停止信號 ({signum})，準備保存並退出...")
    shutdown_requested = True


LEARNING_TRACKS = [
    {
        "name": "精神疾病求生指南",
        "prompt": "我在學習精神疾病求生指南，請輸出：風險訊號、立即步驟、求助資源、今日自助清單，並提出一個下一輪追問。",
        "deep_follow_ups": [
            "基於你剛才提到的，更深層的疑問是什麼？",
            "你打算如何將這些步驟實際應用到日常生活中？",
            "在實施時可能遇到哪些挑戰，該如何應對？",
        ],
    },
    {
        "name": "腦神經科學",
        "prompt": "我在學習腦神經科學，請輸出：核心概念、可驗證問題、下一步學習、24h/7d複習節奏，並提出一個下一輪追問。",
        "deep_follow_ups": [
            "這個概念與你之前學到的知識有什麼連結？",
            "可以設計什麼實驗來驗證這個發現？",
            "這在心理學或臨床應用中有什麼意義？",
        ],
    },
    {
        "name": "聖經學習",
        "prompt": "我在讀聖經，請輸出：經文主題、核心信息、今日應用、禱告/默想建議，並提出一個下一輪追問。",
        "deep_follow_ups": [
            "這段經文對你個人的信仰旅程有什麼啟示？",
            "歷史文脈中這段經文的原始意義是什麼？",
            "如何將這個真理應用到當代生活中？",
        ],
    },
]


def build_round_prompt(track: dict, prev_summary: str, round_index: int) -> str:
    """根據輪數和主題構建提示詞，支持多輪深化追問"""
    track_name = track["name"]
    base_prompt = track["prompt"]

    if round_index == 1 or not prev_summary:
        return base_prompt

    # 基礎延續提示
    context = prev_summary.strip()
    if len(context) > 260:
        context = context[:260] + "..."

    continuation = (
        f"延續上一輪 {track_name} 學習。"
        f"上一輪摘要：{context}。"
        f"請進一步深化並保持可執行性，最後再提出一個下一輪追問。"
    )

    # 根據輪次加入深化追問
    round_within_track = ((round_index - 1) % len(LEARNING_TRACKS)) + 1
    if round_within_track > 1:  # 不是該主題的第一輪
        deep_follow_ups = track.get("deep_follow_ups", [])
        if deep_follow_ups:
            # 選擇該輪的深化追問
            follow_up_index = min(
                (round_within_track - 2) % len(deep_follow_ups),
                len(deep_follow_ups) - 1,
            )
            follow_up = deep_follow_ups[follow_up_index]
            continuation = f"{continuation}\n\n進一步思考：{follow_up}"

    return continuation


def run_learning(rounds: int, interval_sec: float, continuous: bool):
    global shutdown_requested

    # 註冊信號處理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    chat = GeminiMemoryChat()

    if not chat.gemini_client:
        print("\n❌ 無法初始化 Gemini API，請先確認金鑰設定")
        return 1

    if not chat.load_memories():
        print("\n⚠️ 記憶載入失敗，改以無記憶模式繼續")

    print("\n" + "=" * 80)
    print("  🤖 連續自主學習已啟動")
    print("=" * 80)
    mode_text = (
        "持續模式（Ctrl+C 停止）" if continuous else f"固定輪數模式（{rounds} 輪）"
    )
    print(f"模式: {mode_text}")
    print(f"間隔: {interval_sec} 秒")
    print("學習軌道: 精神疾病求生指南 / 腦神經科學 / 聖經")
    print("=" * 80 + "\n")

    round_index = 0
    prev_summary_by_track = {track["name"]: "" for track in LEARNING_TRACKS}

    try:
        while True:
            # 檢查是否收到關閉請求
            if shutdown_requested:
                break

            round_index += 1
            track = LEARNING_TRACKS[(round_index - 1) % len(LEARNING_TRACKS)]
            track_name = track["name"]

            user_prompt = build_round_prompt(
                track=track,
                prev_summary=prev_summary_by_track[track_name],
                round_index=round_index,
            )

            print(f"🧠 第 {round_index} 輪 | 主題: {track_name}")
            print("-" * 80)
            print(
                f"Prompt: {user_prompt[:120]}{'...' if len(user_prompt) > 120 else ''}"
            )

            response = chat.chat(user_prompt)
            print(f"Response: {response[:200]}{'...' if len(response) > 200 else ''}")

            if chat._is_learning_turn(user_prompt):
                extracted = chat._extract_learning_points_from_turn(
                    user_prompt, response
                )
                chat.learning_extractions.append(extracted)
                print(chat._format_learning_template(extracted))

            prev_summary_by_track[track_name] = response
            print()

            if not continuous and round_index >= rounds:
                break

            # 在睡眠期間也檢查關閉請求
            sleep_start = time.time()
            while time.time() - sleep_start < interval_sec:
                if shutdown_requested:
                    break
                time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n🛑 已收到停止指令，準備保存學習紀錄...")
    finally:
        if chat.conversation_history:
            chat.save_conversation()
            print("✅ 已保存連續自主學習會話")

    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="連續自主學習引擎")
    parser.add_argument("--rounds", type=int, default=6, help="固定模式輪數（預設 6）")
    parser.add_argument(
        "--interval", type=float, default=1.0, help="每輪間隔秒數（預設 1.0）"
    )
    parser.add_argument(
        "--continuous", action="store_true", help="持續模式，直到手動中斷"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.rounds <= 0 and not args.continuous:
        print("❌ rounds 必須大於 0，或使用 --continuous")
        return 1
    return run_learning(
        rounds=args.rounds, interval_sec=args.interval, continuous=args.continuous
    )


if __name__ == "__main__":
    sys.exit(main())
