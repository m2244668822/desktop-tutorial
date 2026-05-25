#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
對話記錄示例 - 展示如何使用對話記錄系統
"""

from conversation_logger import ConversationLogger


def example_basic_logging():
    """基本對話記錄示例"""
    print("=== 示例 1: 基本對話記錄 ===\n")

    logger = ConversationLogger()

    # 記錄一次對話
    conv_id = logger.log_conversation(
        user_message="如何提升 Python 代碼的可讀性？",
        assistant_response="""
        提升 Python 代碼可讀性的方法：
        
        1. 使用有意義的變量名
        2. 保持函數簡潔（單一責任原則）
        3. 添加適當的註釋和文檔字符串
        4. 遵循 PEP 8 風格指南
        5. 使用列表推導式而不是 for 循環
        6. 適當的空白和縮進
        """,
        tags=["python", "coding-style", "best-practices"],
        context={"topic": "code-quality"},
    )

    print(f"✅ 對話已記錄: {conv_id}\n")


def example_programming_session():
    """編程會話記錄示例"""
    print("=== 示例 2: 編程會話記錄 ===\n")

    logger = ConversationLogger()

    session_id = logger.log_programming_session(
        task_description="實現用戶認證 API",
        code_changes=[
            {
                "file": "app/auth.py",
                "description": "添加 JWT token 生成函數",
                "lines_added": 45,
                "lines_deleted": 0,
            },
            {
                "file": "app/routes.py",
                "description": "添加登錄和註冊端點",
                "lines_added": 32,
                "lines_deleted": 5,
            },
            {
                "file": "tests/test_auth.py",
                "description": "添加認證功能單元測試",
                "lines_added": 67,
                "lines_deleted": 0,
            },
        ],
        solutions=[
            "使用 PyJWT 庫生成和驗證 JWT token",
            "密碼使用 bcrypt 進行 hash 處理",
            "實現 token 刷新機制",
            "添加請求頻率限制防止暴力破解",
        ],
        learnings=[
            "JWT token 包含 header、payload 和 signature 三部分",
            "token 應該設置合理的過期時間（如 15 分鐘）",
            "refresh token 可以有更長的有效期（如 7 天）",
            "bcrypt 的 salt rounds 建議設置為 12",
            "密碼驗證失敗應該返回通用的錯誤信息避免洩露用戶是否存在",
        ],
    )

    print(f"✅ 編程會話已記錄: {session_id}\n")


def example_learning_note():
    """學習筆記示例"""
    print("=== 示例 3: 添加學習筆記 ===\n")

    logger = ConversationLogger()

    logger.add_learning_note(
        topic="Git 工作流最佳實踐",
        content="""
        學到的 Git 最佳實踐：
        
        1. 提交消息格式
           - type(scope): subject
           - 例如：feat(auth): add JWT authentication
        
        2. 分支策略
           - main: 穩定版本
           - develop: 開發版本
           - feature/*: 功能分支
           - hotfix/*: 緊急修復
        
        3. 提交頻率
           - 小而頻繁的提交優於大的提交
           - 每個提交應該是一個邏輯單元
        
        4. 代碼審查
           - 創建 Pull Request 前先自己審查
           - PR 應該專注於單一功能或修復
        """,
        category="development",
    )

    print("✅ 學習筆記已添加\n")


def example_export_data():
    """導出學習數據示例"""
    print("=== 示例 4: 導出學習數據 ===\n")

    logger = ConversationLogger()

    # 獲取摘要
    summary = logger.get_learning_summary()
    print("📊 學習摘要:")
    print(f"   總對話數: {summary['total_conversations']}")
    print(f"   總會話數: {summary['total_sessions']}")
    print(f"   總筆記數: {summary['total_notes']}")

    if summary["popular_tags"]:
        print(f"   熱門標籤:")
        for tag, count in summary["popular_tags"][:5]:
            print(f"      - {tag}: {count} 次")

    print()

    # 導出數據
    logger.export_learning_data("example_export.json")


def example_quick_log():
    """快速記錄示例"""
    print("=== 示例 5: 快速記錄 ===\n")

    from conversation_logger import quick_log

    # 使用便捷函數快速記錄
    quick_log(
        user_msg="什麼是依賴注入？",
        assistant_msg="依賴注入是一種設計模式，用於實現控制反轉（IoC）。它通過將依賴關係從類內部移到外部來提高代碼的可測試性和靈活性。",
        tags=["design-pattern", "dependency-injection"],
    )

    print()


def main():
    """運行所有示例"""
    print("\n" + "=" * 60)
    print("🎓 對話記錄系統使用示例")
    print("=" * 60 + "\n")

    try:
        example_basic_logging()
        example_programming_session()
        example_learning_note()
        example_export_data()
        example_quick_log()

        print("=" * 60)
        print("✅ 所有示例運行完成！")
        print("=" * 60)
        print("\n💡 查看生成的數據:")
        print("   - data/conversations.json")
        print("   - data/learning_log.json")
        print("   - data/example_export.json")
        print("\n📖 完整文檔: docs/09_對話記錄使用指南.md\n")

    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
