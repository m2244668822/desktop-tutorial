#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent.parent.parent
DB_PATH = (
    BASE_DIR / "500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json"
)


def format_time(ts):
    if not ts:
        return "未知時間"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def get_conversation(target_title):
    if not DB_PATH.exists():
        return "錯誤: 找不到資料庫。"

    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            full_data = json.load(f)
            conversations = full_data.get("data", {}).get("conversations", [])

            for conv in conversations:
                if conv.get("title") == target_title:
                    mapping = conv.get("mapping", {})
                    messages = []

                    for node_id, node in mapping.items():
                        msg = node.get("message")
                        if msg and msg.get("content"):
                            role = msg.get("author", {}).get("role", "unknown")
                            create_time = msg.get("create_time", 0)

                            parts = msg.get("content", {}).get("parts", [])
                            content = "".join(
                                [p if isinstance(p, str) else "" for p in parts]
                            ).strip()

                            if content:
                                messages.append(
                                    {"time": create_time, "role": role, "text": content}
                                )

                    # 排序對話
                    messages.sort(key=lambda x: x["time"])

                    output = [
                        f"\n{'=' * 60}",
                        f"📜 對話回溯: {target_title}",
                        f"📅 訊息總數: {len(messages)} 條",
                        f"{'=' * 60}\n",
                    ]

                    for m in messages:
                        role_tag = "👤 [YOU]" if m["role"] == "user" else "🤖 [GPT]"
                        time_str = format_time(m["time"])
                        output.append(f"{role_tag}  ({time_str})")
                        output.append(f"{m['text']}\n")
                        output.append("-" * 30 + "\n")

                    return "\n".join(output)

            return f"❌ 找不到標題: {target_title}"
    except Exception as e:
        return f"讀取失敗: {e}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 get_conversation.py <完整對話標題>")
    else:
        title = " ".join(sys.argv[1:])
        print(get_conversation(title))
