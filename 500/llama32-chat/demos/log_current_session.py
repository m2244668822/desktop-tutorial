#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
記錄當前對話會話的腳本
可手動運行以記錄與 AI 助手的對話
"""

from conversation_logger import ConversationLogger


def log_todays_session():
    """記錄今天的對話會話"""
    logger = ConversationLogger()

    print("=== 記錄今天的對話會話 ===\n")

    # 記錄今天的主要會話：文檔整合
    session_id = logger.log_programming_session(
        task_description="整合和清理系統文檔結構",
        code_changes=[
            {
                "file": "README.md",
                "description": "更新文檔導航連結，指向統一的 docs/ 資料夾",
            },
            {
                "file": "SYSTEM_OVERVIEW.md",
                "description": "簡化文檔表格，保留三份核心文檔連結",
            },
            {"file": "docs/04_功能介紹.md", "description": "新增完整功能介紹文檔"},
            {"file": "docs/05_監測系統.md", "description": "新增監測系統說明文檔"},
            {"file": "docs/06_架構設計.md", "description": "新增詳細架構設計文檔"},
            {"file": "docs/07_整合指南.md", "description": "新增整合步驟指南文檔"},
            {"file": "docs/08_優化建議.md", "description": "新增性能優化建議文檔"},
            {"file": "docs/00_文檔索引.md", "description": "新增文檔索引和導航系統"},
        ],
        solutions=[
            "統一文檔到 docs/ 單一資料夾",
            "刪除 docs_backup/ 和 docs_organized/ 等冗餘資料夾",
            "刪除根目錄下的重複 md 文件（保留核心三份）",
            "編號命名文件（00-08）提升可讀性",
            "創建完整的中文文檔體系（功能、監測、架構、整合、優化）",
            "刪除空的子資料夾避免 VS Code 顯示問題",
        ],
        learnings=[
            "文檔整合需要統一的結構和命名規範",
            "使用編號前綴（00_, 01_, 02_）可以保持文件順序",
            "空資料夾會導致編輯器顯示異常，需要及時清理",
            "刪除空資料夾命令：find . -type d -empty -delete",
            "保留根目錄核心文檔的副本在子資料夾中",
            "按角色和主題組織文檔索引更容易導航",
            "中文路徑可能導致終端顯示問題，但不影響功能",
            "macOS 中文路徑在終端顯示為編碼字符是正常的",
        ],
    )

    print(f"\n✅ 會話已記錄: {session_id}")

    # 添加關鍵學習筆記
    logger.add_learning_note(
        topic="VS Code 文件夾顯示問題",
        content="""
當 VS Code 中看到折疊的資料夾名稱（如「完整指南」「快速開始」）但打開是空的時候，
這些是空的子資料夾，不是 md 文件。

解決方法：
1. 在終端執行：find . -type d -empty -delete
2. 刷新 VS Code 界面
3. 確認看到的是 .md 文件而不是資料夾

根本原因：
之前的整合過程中創建了分類資料夾，但後來改成統一結構時沒有刪除這些空資料夾。
        """,
        category="debugging",
    )

    logger.add_learning_note(
        topic="文檔結構設計原則",
        content="""
好的文檔結構應該：
1. 單一入口：使用索引文檔（00_文檔索引.md）統一導航
2. 按順序編號：00-08 保持邏輯順序
3. 按角色分類：新用戶、開發者、架構師、運維人員
4. 按主題分類：入門、核心技術、部署、監控、優化
5. 避免冗餘：刪除重複和過時的文檔
6. 保持更新：及時同步根目錄和子目錄的文檔
        """,
        category="documentation",
    )

    logger.add_learning_note(
        topic="對話記錄學習系統",
        content="""
實現對話記錄系統使智能體能從對話中學習：

核心組件：
1. ConversationLogger 類 - 記錄對話和編程會話
2. learning_log.json - 專門存儲學習數據
3. conversations.json - 存儲所有對話（包含學習標記）

功能：
- log_conversation: 記錄單次對話
- log_programming_session: 記錄完整編程會話（任務、代碼變更、解決方案、學習要點）
- add_learning_note: 添加學習筆記
- export_learning_data: 導出所有學習數據
- get_learning_summary: 獲取學習摘要統計

使用場景：
- 每次與 AI 助手對話後手動記錄
- 完成編程任務後總結學習要點
- 遇到問題並解決後記錄經驗
- 定期導出學習數據進行分析
        """,
        category="architecture",
    )

    # 顯示學習摘要
    print("\n=== 學習摘要 ===")
    summary = logger.get_learning_summary()
    print(f"總對話數: {summary['total_conversations']}")
    print(f"總會話數: {summary['total_sessions']}")
    print(f"總筆記數: {summary['total_notes']}")
    if summary["popular_tags"]:
        print(
            f"熱門標籤: {', '.join([f'{tag}({count})' for tag, count in summary['popular_tags'][:5]])}"
        )

    # 導出學習數據
    print("\n=== 導出學習數據 ===")
    logger.export_learning_data("learning_data_20260227.json")

    print("\n✅ 今天的會話記錄完成！")
    print("\n💡 提示：")
    print("- 查看對話記錄：data/conversations.json")
    print("- 查看學習日誌：data/learning_log.json")
    print("- 查看導出數據：data/learning_data_20260227.json")
    print("\n你可以執行 'python chat.py \"總結我最近的學習內容\"' 讓 AI 分析這些數據")


if __name__ == "__main__":
    log_todays_session()
