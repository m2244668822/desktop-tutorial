#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# 設定基礎路徑
BASE_DIR = Path(__file__).parent.parent.parent.parent
DB_PATH = (
    BASE_DIR / "500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json"
)


class MemoryOptimizer:
    def __init__(self, db_path):
        self.db_path = db_path
        self.data = None

    def load_data(self):
        """緩存加載，避免多次執行時重複讀取"""
        if self.data is None:
            if not self.db_path.exists():
                raise FileNotFoundError(f"找不到資料庫: {self.db_path}")
            with open(self.db_path, "r", encoding="utf-8") as f:
                full_data = json.load(f)
                self.data = full_data.get("data", {}).get("conversations", [])
        return self.data

    def quick_search(self, query):
        conversations = self.load_data()
        query_re = re.compile(re.escape(query), re.IGNORECASE)
        results = []

        for conv in conversations:
            if not isinstance(conv, dict):
                continue

            title = conv.get("title", "") or "無標題"
            title_match = query_re.search(title)

            content_matches = []
            mapping = conv.get("mapping", {})

            # 優化搜尋：只搜尋有訊息內容的部分
            for node in mapping.values():
                msg = node.get("message")
                if msg and msg.get("content"):
                    parts = msg.get("content", {}).get("parts", [])
                    for part in parts:
                        if isinstance(part, str) and query_re.search(part):
                            content_matches.append(part)

            if title_match or content_matches:
                results.append(
                    {
                        "title": title,
                        "matches": len(content_matches),
                        "preview": content_matches[0][:150].strip() + "..."
                        if content_matches
                        else "匹配於標題",
                    }
                )

        # 排序：匹配次數 > 標題匹配
        results.sort(key=lambda x: x["matches"], reverse=True)
        return results


def main():
    if len(sys.argv) < 2:
        print("用法: python3 search_memory.py <關鍵字>")
        return

    query = " ".join(sys.argv[1:])
    optimizer = MemoryOptimizer(DB_PATH)

    try:
        results = optimizer.quick_search(query)
        if not results:
            print(f"❌ 找不到與 '{query}' 相關的內容。")
            return

        print(f"✅ 找到 {len(results)} 條紀錄：\n" + "=" * 50)
        for i, res in enumerate(results[:15]):  # 顯示前 15 條
            print(f"{i + 1:2}. 【{res['title']}】 ({res['matches']} 次匹配)")
            print(f"    摘要: {res['preview']}\n" + "-" * 30)

        if len(results) > 15:
            print(f"... 還有 {len(results) - 15} 條結果隱藏中。")

    except Exception as e:
        print(f"發生錯誤: {e}")


if __name__ == "__main__":
    main()
