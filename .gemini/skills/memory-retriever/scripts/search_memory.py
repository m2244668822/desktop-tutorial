#!/usr/bin/env python3
import json
import sys
import os
from pathlib import Path

# 設定基礎路徑
BASE_DIR = Path(__file__).parent.parent.parent.parent
DB_PATH = BASE_DIR / "500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json"

def search_database(query):
    if not DB_PATH.exists():
        return f"錯誤: 找不到數據庫檔案 {DB_PATH}"

    print(f"🔍 正在搜尋: '{query}'...")
    results = []
    
    try:
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # 假設數據結構是列表 [{title: "", messages: [...]}, ...]
            for conv in data:
                found_in_title = query.lower() in conv.get('title', '').lower()
                
                # 搜尋消息內容
                matches = []
                for msg in conv.get('messages', []):
                    content = msg.get('content', '')
                    if query.lower() in content.lower():
                        matches.append(content)
                
                if found_in_title or matches:
                    results.append({
                        'title': conv.get('title', '無標題'),
                        'match_count': len(matches),
                        'preview': matches[0][:100] + "..." if matches else "匹配於標題"
                    })
    except Exception as e:
        return f"搜尋過程中發生錯誤: {e}"

    if not results:
        return "❌ 找不到相關紀錄。"

    # 按匹配次數排序
    results.sort(key=lambda x: x['match_count'], reverse=True)
    
    output = [f"✅ 找到 {len(results)} 條相關對話：\n"]
    for i, res in enumerate(results[:10]):  # 只顯示前 10 條
        output.append(f"{i+1}. 【{res['title']}】 (匹配 {res['match_count']} 次)")
        output.append(f"   預覽: {res['preview']}\n")
    
    if len(results) > 10:
        output.append(f"... 還有 {len(results)-10} 條結果未顯示。")
        
    return "\n".join(output)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("請提供搜尋關鍵字。用法: python3 search_memory.py <關鍵字>")
    else:
        query = " ".join(sys.argv[1:])
        print(search_database(query))
