"""
ChatGPT 本地化完整流程 - 導入 → 驗證 → 索引 → 集成
整合所有步驟，一鍵完成 ChatGPT 數據本地化
"""

import sys
from pathlib import Path
from typing import Dict, List, Any

# 確保可以導入本地模塊
sys.path.insert(0, str(Path(__file__).parent))

from chatgpt_importer import ChatGPTImporter
from rag_pipeline import RAGPipeline
from utils import JsonStorage, TimeHelper, PrintHelper
from constants import (
    CONVERSATION_FILE,
    DATA_DIR,
    RAG_DB_DIR,
    RAG_COLLECTION,
    RAG_EMBED_MODEL,
)


class ChatGPTLocalizer:
    """ChatGPT 本地化管理器 - 完整的導入、索引、管理流程"""

    def __init__(self):
        self.importer = ChatGPTImporter()
        self.rag_pipeline = RAGPipeline(
            db_dir=RAG_DB_DIR,
            collection_name=RAG_COLLECTION,
            embed_model=RAG_EMBED_MODEL,
        )

    def import_and_index(
        self, file_path: Path, rebuild_index: bool = False
    ) -> Dict[str, Any]:
        """
        完整的導入和索引流程

        Args:
            file_path: 數據源文件路徑
            rebuild_index: 是否重建 RAG 索引

        Returns:
            操作結果和統計
        """
        print("\n" + "=" * 80)
        PrintHelper.header("🚀 ChatGPT 本地化完整流程", width=80)
        print("=" * 80)

        result = {
            "success": False,
            "import_result": None,
            "index_result": None,
            "total_conversations": 0,
            "message": "",
        }

        try:
            # 第一步：導入數據
            print("\n📥 第一步：導入 ChatGPT 數據...")
            print("-" * 80)
            import_result = self.importer.import_from_file(file_path)
            result["import_result"] = import_result

            if not import_result["success"]:
                result["message"] = import_result["message"]
                return result

            # 第二步：構建 RAG 索引
            print("\n🔍 第二步：構建 RAG 索引...")
            print("-" * 80)

            conversations = JsonStorage.load(CONVERSATION_FILE, default=[])
            if not conversations:
                result["message"] = "❌ 沒有對話數據可索引"
                return result

            print(f"📚 正在索引 {len(conversations)} 條對話...")

            try:
                # 解析對話以供 RAG 使用
                from rag_pipeline import _parse_conversations

                documents, metadatas, ids = _parse_conversations(conversations)

                print(f"✅ 解析了 {len(documents)} 條文檔")

                # 構建集合
                collection = self.rag_pipeline._get_collection(rebuild=rebuild_index)

                if rebuild_index:
                    print("🔄 重建索引...")
                else:
                    print("➕ 添加到現有索引...")

                # 分批添加（避免超時）
                batch_size = 50
                for i in range(0, len(documents), batch_size):
                    batch_docs = documents[i : i + batch_size]
                    batch_meta = metadatas[i : i + batch_size]
                    batch_ids = ids[i : i + batch_size]

                    collection.add(
                        documents=batch_docs, metadatas=batch_meta, ids=batch_ids
                    )

                    progress = min(i + batch_size, len(documents))
                    print(f"  進度: {progress}/{len(documents)} ✓")

                print(f"✅ RAG 索引構建完成！")
                result["index_result"] = {
                    "success": True,
                    "indexed": len(documents),
                    "message": "✅ 索引構建成功",
                }

            except ImportError as e:
                if "chromadb" in str(e):
                    print(f"\n⚠️  Chroma 未安裝，跳過 RAG 索引構建")
                    print(
                        f"   如需使用 RAG 功能，請運行: pip install chromadb sentence-transformers"
                    )
                    result["index_result"] = {
                        "success": False,
                        "message": "⚠️  Chroma 未安裝",
                    }
                else:
                    raise

            # 第三步：生成統計報告
            print("\n📊 第三步：統計和驗證...")
            print("-" * 80)

            conversations = JsonStorage.load(CONVERSATION_FILE, default=[])
            result["total_conversations"] = len(conversations)

            stats = self._generate_stats(conversations)
            self._print_stats(stats)

            result["success"] = True
            result["message"] = (
                f"✅ 本地化完成！共 {result['total_conversations']} 條對話"
            )

            # 打印最終總結
            print("\n" + "=" * 80)
            PrintHelper.header("✨ 本地化完成", width=80)
            print("=" * 80)
            print(f"✅ 導入新對話: {import_result['imported']}")
            print(f"✅ 移除重複: {import_result['duplicates']}")
            print(f"✅ 總對話數: {result['total_conversations']}")
            if result["index_result"] and result["index_result"]["success"]:
                print(f"✅ 已索引: {result['index_result']['indexed']}")
            print("=" * 80 + "\n")

            return result

        except Exception as e:
            result["message"] = f"❌ 本地化失敗: {str(e)}"
            print(f"\n{result['message']}")
            import traceback

            traceback.print_exc()
            return result

    def _generate_stats(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成統計信息"""
        stats = {
            "total": len(conversations),
            "by_model": {},
            "by_status": {},
            "date_range": {},
            "avg_prompt_length": 0,
            "avg_response_length": 0,
        }

        if not conversations:
            return stats

        models = {}
        statuses = {}
        prompt_lengths = []
        response_lengths = []
        timestamps = []

        for conv in conversations:
            # 按模型計數
            model = conv.get("model", "unknown")
            models[model] = models.get(model, 0) + 1

            # 按狀態計數
            status = conv.get("status", "unknown")
            statuses[status] = statuses.get(status, 0) + 1

            # 長度統計
            prompt_lengths.append(len(conv.get("prompt", "")))
            response_lengths.append(len(conv.get("response", "")))

            # 時間戳
            if "timestamp" in conv:
                timestamps.append(conv["timestamp"])

        stats["by_model"] = models
        stats["by_status"] = statuses
        stats["avg_prompt_length"] = (
            sum(prompt_lengths) / len(prompt_lengths) if prompt_lengths else 0
        )
        stats["avg_response_length"] = (
            sum(response_lengths) / len(response_lengths) if response_lengths else 0
        )

        if timestamps:
            stats["date_range"] = {
                "earliest": min(timestamps),
                "latest": max(timestamps),
            }

        return stats

    def _print_stats(self, stats: Dict[str, Any]):
        """打印統計信息"""
        print(f"\n📊 數據統計：")
        print(f"   總數: {stats['total']}")

        if stats["by_model"]:
            print(f"\n   按模型分類:")
            for model, count in stats["by_model"].items():
                print(f"     {model}: {count}")

        if stats["by_status"]:
            print(f"\n   按狀態分類:")
            for status, count in stats["by_status"].items():
                print(f"     {status}: {count}")

        print(f"\n   平均提示長度: {stats['avg_prompt_length']:.0f} 字符")
        print(f"   平均回應長度: {stats['avg_response_length']:.0f} 字符")

        if stats["date_range"]:
            print(f"\n   時間範圍:")
            print(f"     最早: {stats['date_range']['earliest']}")
            print(f"     最新: {stats['date_range']['latest']}")

    def get_summary(self) -> Dict[str, Any]:
        """獲取當前本地化狀態摘要"""
        conversations = JsonStorage.load(CONVERSATION_FILE, default=[])
        import_stats = self.importer.get_import_stats()

        return {
            "total_conversations": len(conversations),
            "import_stats": import_stats,
            "last_sync": TimeHelper.now_iso(),
            "storage_location": str(CONVERSATION_FILE),
            "rag_enabled": RAG_DB_DIR.exists(),
        }


def interactive_import():
    """交互式導入流程"""
    print("\n" + "=" * 80)
    PrintHelper.header("🤖 ChatGPT 本地化工具", width=80)
    print("=" * 80)

    localizer = ChatGPTLocalizer()

    while True:
        print("\n請選擇操作：")
        print("1️⃣  導入 ChatGPT 數據（推薦首次使用）")
        print("2️⃣  查看本地化狀態")
        print("3️⃣  導入統計")
        print("4️⃣  測試 API 連接")
        print("5️⃣  退出")

        choice = input("\n請選擇 (1-5): ").strip()

        if choice == "1":
            file_path_input = input(
                "\n📁 請輸入 JSON 文件路徑 (或按Enter取消): "
            ).strip()
            if not file_path_input:
                print("⏭️  已取消")
                continue

            file_path = Path(file_path_input)
            if not file_path.exists():
                print(f"❌ 文件不存在: {file_path_input}")
                continue

            rebuild = input("是否重建 RAG 索引? (y/n, 預設 n): ").strip().lower() == "y"
            result = localizer.import_and_index(file_path, rebuild_index=rebuild)

            if result["success"]:
                print(f"\n✅ {result['message']}")
            else:
                print(f"\n❌ {result['message']}")

        elif choice == "2":
            print("\n📊 本地化狀態：")
            summary = localizer.get_summary()
            print(f"   總對話數: {summary['total_conversations']}")
            print(f"   最後同步: {summary['last_sync']}")
            print(f"   存儲位置: {summary['storage_location']}")
            print(
                f"   RAG 索引: {'✅ 已啟用' if summary['rag_enabled'] else '⏸️  未啟用'}"
            )

        elif choice == "3":
            stats = localizer.importer.get_import_stats()
            print("\n📈 導入統計：")
            print(f"   導入次數: {stats['total_imports']}")
            print(f"   累計導入: {stats['total_imported']}")
            if stats["last_import"]:
                print(f"   最後導入: {stats['last_import']['timestamp']}")

        elif choice == "4":
            print("\n🔍 測試 API 連接...")
            if localizer.importer.api_client.test_connection():
                print("✅ OpenAI API 連接成功！")
            else:
                print("❌ OpenAI API 連接失敗")

        elif choice == "5":
            print("👋 再見！")
            break

        else:
            print("❌ 無效選擇，請重試")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ChatGPT 本地化工具 - 導入、索引、管理您的 ChatGPT 對話",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 交互式導入
  python chatgpt_localizer.py
  
  # 直接導入文件
  python chatgpt_localizer.py -f conversations.json
  
  # 導入並重建索引
  python chatgpt_localizer.py -f conversations.json --rebuild-index
        """,
    )

    parser.add_argument("-f", "--file", type=str, help="JSON 文件路徑（自動導入模式）")

    parser.add_argument("--rebuild-index", action="store_true", help="重建 RAG 索引")

    args = parser.parse_args()

    if args.file:
        # 自動導入模式
        localizer = ChatGPTLocalizer()
        file_path = Path(args.file)

        if not file_path.exists():
            print(f"❌ 文件不存在: {args.file}")
            sys.exit(1)

        result = localizer.import_and_index(file_path, rebuild_index=args.rebuild_index)
        sys.exit(0 if result["success"] else 1)
    else:
        # 交互模式
        try:
            interactive_import()
        except KeyboardInterrupt:
            print("\n\n⚠️  用戶中止")
            sys.exit(1)
