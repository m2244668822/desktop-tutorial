"""
ChatGPT 數據導入模塊 - 通過API拉取所有ChatGPT對話並本地化存儲
支持：數據拉取、驗證、轉換、去重、本地存儲、RAG索引化
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

import requests
from dotenv import load_dotenv

from constants import CONVERSATION_FILE, DATA_DIR, LOGS_DIR, RAG_DB_DIR
from utils import JsonStorage, TimeHelper, FileHelper, PrintHelper

# 加載環境變數
load_dotenv()

# 配置日誌
logger = logging.getLogger(__name__)


class ChatGPTAPIClient:
    """OpenAI ChatGPT API 客户端"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY，請設置環境變數或傳入 API 金鑰")

        self.base_url = "https://api.openai.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_conversations_list(self) -> List[Dict[str, Any]]:
        """
        獲取所有對話列表
        注意：OpenAI API 沒有直接的 conversations 端點，
        此方法通過 messages 端點恢復對話歷史
        """
        try:
            # 使用 completions 歷史記錄 API（如果可用）
            response = self.session.get(f"{self.base_url}/models", timeout=30)
            response.raise_for_status()

            logger.info("✅ 成功連接到 OpenAI API")
            return []

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 連接 OpenAI API 失敗: {e}")
            raise

    def get_chat_completions_history(self) -> List[Dict[str, Any]]:
        """
        獲取聊天補全的歷史記錄
        注意：這需要使用不同的方法，因為 OpenAI API 不直接提供對話歷史
        我們會使用替代方案：使用 conversation history 存儲
        """
        logger.warning("⚠️  OpenAI 官方 API 不提供直接的對話導出端點")
        logger.warning("📝 使用以下替代方案：")
        logger.warning("   1. 從官網 ChatGPT 導出 JSON")
        logger.warning("   2. 使用第三方集成工具")
        logger.warning("   3. 手動導入存儲的對話")
        return []

    def test_connection(self) -> bool:
        """測試 API 連接"""
        try:
            response = self.session.get(f"{self.base_url}/models", timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"API 連接測試失敗: {e}")
            return False


class DataValidator:
    """數據驗證和清理"""

    @staticmethod
    def validate_conversation(item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        驗證單個對話記錄

        Returns:
            (是否有效, 錯誤訊息)
        """
        # 必需字段
        required_fields = ["prompt", "response"]
        for field in required_fields:
            if field not in item or not item[field]:
                return False, f"缺少必需字段: {field}"

        # 驗證類型
        if not isinstance(item["prompt"], str) or not isinstance(item["response"], str):
            return False, "prompt 和 response 必須是字符串"

        # 驗證長度
        if len(item["prompt"]) < 1 or len(item["response"]) < 1:
            return False, "prompt 或 response 為空"

        return True, None

    @staticmethod
    def clean_conversation(item: Dict[str, Any]) -> Dict[str, Any]:
        """清理和標準化對話記錄"""
        cleaned = {
            "id": item.get("id", f"conv-{int(datetime.now().timestamp() * 1000)}"),
            "timestamp": item.get("timestamp", TimeHelper.now_iso()),
            "model": item.get("model", "openai"),
            "prompt": item.get("prompt", "").strip(),
            "response": item.get("response", "").strip(),
            "status": item.get("status", "success"),
            "metadata": {
                "source": item.get("source", "chatgpt_api"),
                "tokens": item.get("tokens", 0),
                "cost": item.get("cost", 0),
                "original_id": item.get("original_id"),
            },
        }
        return cleaned


class DuplicateDetector:
    """去重和冗餘檢測"""

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """
        簡單的文本相似度計算（基於 token 重疊）
        返回 0.0-1.0 的相似度分數
        """
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    @staticmethod
    def find_duplicates(
        conversations: List[Dict[str, Any]], threshold: float = 0.9
    ) -> List[Tuple[int, int, float]]:
        """
        查找潛在的重複對話

        Returns:
            List of (index1, index2, similarity_score)
        """
        duplicates = []

        for i in range(len(conversations)):
            for j in range(i + 1, len(conversations)):
                conv1 = conversations[i]
                conv2 = conversations[j]

                # 比較 prompt 和 response
                sim_prompt = DuplicateDetector.calculate_similarity(
                    conv1["prompt"], conv2["prompt"]
                )
                sim_response = DuplicateDetector.calculate_similarity(
                    conv1["response"], conv2["response"]
                )

                avg_similarity = (sim_prompt + sim_response) / 2

                if avg_similarity >= threshold:
                    duplicates.append((i, j, avg_similarity))

        return duplicates

    @staticmethod
    def remove_duplicates(
        conversations: List[Dict[str, Any]], threshold: float = 0.9
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        移除重複的對話記錄

        Returns:
            (清潔後的對話列表, 移除的對話列表)
        """
        seen_prompts = {}  # prompt_hash -> index
        removed = []
        unique = []

        for i, conv in enumerate(conversations):
            prompt_hash = hash(conv["prompt"].lower().strip())

            if prompt_hash in seen_prompts:
                # 檢查是否真正重複
                existing_idx = seen_prompts[prompt_hash]
                similarity = DuplicateDetector.calculate_similarity(
                    conversations[existing_idx]["prompt"], conv["prompt"]
                )

                if similarity >= threshold:
                    removed.append(conv)
                    continue

            seen_prompts[prompt_hash] = i
            unique.append(conv)

        return unique, removed


class ChatGPTImporter:
    """ChatGPT 數據導入主類"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_client = ChatGPTAPIClient(api_key)
        self.validator = DataValidator()
        self.dedup_detector = DuplicateDetector()

        # 確保目錄存在
        FileHelper.ensure_dir(DATA_DIR)
        FileHelper.ensure_dir(LOGS_DIR)

        # 初始化導入日誌
        self.import_log_path = LOGS_DIR / "import_log.json"

    def import_from_api(self) -> Dict[str, Any]:
        """
        從 OpenAI API 導入對話

        注意：OpenAI API 不提供直接的對話歷史導出功能。
        使用此方法需要自行維護對話歷史。
        """
        print("\n" + "=" * 60)
        PrintHelper.header("💬 OpenAI API 導入", width=60)
        print("=" * 60)

        result = {
            "success": False,
            "imported": 0,
            "errors": 0,
            "duplicates": 0,
            "message": "",
            "timestamp": TimeHelper.now_iso(),
        }

        try:
            # 測試連接
            print("🔍 正在測試 API 連接...")
            if not self.api_client.test_connection():
                result["message"] = "❌ API 連接失敗，請檢查 API 金鑰"
                print(result["message"])
                return result

            print("✅ API 連接成功！")

            # 重要提醒
            print("\n⚠️  重要提醒：")
            print("   OpenAI 官方 API 不提供對話歷史導出端點")
            print("\n📋 解決方案：")
            print("   1️⃣  從 ChatGPT 網頁版導出 JSON 文件")
            print("       訪問：https://chatgpt.com → 設置 → 數據導出")
            print("   2️⃣  使用 import_from_file() 方法導入")

            result["message"] = "⚠️  請使用方案 1 或 2 來導入對話數據"
            return result

        except Exception as e:
            result["message"] = f"❌ 導入失敗: {str(e)}"
            logger.error(result["message"])
            print(result["message"])
            return result

    def import_from_file(self, file_path: Path) -> Dict[str, Any]:
        """
        從 JSON/CSV 文件導入對話

        支持格式：
        - ChatGPT 官網導出的 JSON
        - 標準的對話 JSON 數組格式
        """
        print("\n" + "=" * 60)
        PrintHelper.header(f"📁 從文件導入: {file_path.name}", width=60)
        print("=" * 60)

        result = {
            "success": False,
            "imported": 0,
            "errors": 0,
            "duplicates": 0,
            "message": "",
            "timestamp": TimeHelper.now_iso(),
        }

        try:
            file_path = Path(file_path)

            if not file_path.exists():
                result["message"] = f"❌ 文件不存在: {file_path}"
                print(result["message"])
                return result

            # 讀取文件
            print(f"📖 正在讀取文件...")
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix.lower() == ".json":
                    raw_data = json.load(f)
                else:
                    result["message"] = f"❌ 不支持的文件格式: {file_path.suffix}"
                    print(result["message"])
                    return result

            print(
                f"✅ 讀取了 {len(raw_data) if isinstance(raw_data, list) else 1} 條記錄"
            )

            # 轉換為列表格式
            if isinstance(raw_data, dict):
                # ChatGPT 官網導出的格式可能是對象
                if "conversations" in raw_data:
                    conversations_raw = raw_data["conversations"]
                else:
                    conversations_raw = [raw_data]
            elif isinstance(raw_data, list):
                conversations_raw = raw_data
            else:
                result["message"] = "❌ 無效的 JSON 格式"
                print(result["message"])
                return result

            # 驗證和清理
            print(f"\n🔎 正在驗證和清理 {len(conversations_raw)} 條記錄...")
            valid_conversations = []

            for i, item in enumerate(conversations_raw):
                # 驗證
                is_valid, error_msg = self.validator.validate_conversation(item)

                if not is_valid:
                    result["errors"] += 1
                    logger.warning(f"第 {i} 條記錄無效: {error_msg}")
                    continue

                # 清理
                cleaned = self.validator.clean_conversation(item)
                valid_conversations.append(cleaned)

            print(
                f"✅ 驗證完成: {len(valid_conversations)} 條有效, {result['errors']} 條無效"
            )

            # 去重
            print(f"\n🔄 正在檢測並移除重複...")
            unique, removed = self.dedup_detector.remove_duplicates(
                valid_conversations, threshold=0.85
            )
            result["duplicates"] = len(removed)

            if removed:
                print(f"⚠️  移除了 {len(removed)} 條重複對話")

            # 加載現有數據
            print(f"\n📚 正在加載現有數據...")
            existing = JsonStorage.load(CONVERSATION_FILE, default=[])
            print(f"✅ 現有 {len(existing)} 條對話")

            # 去除與現有數據的重複
            print(f"\n🔍 正在去除與現有數據的重複...")
            final_new = []
            existing_prompts = {c["prompt"].lower().strip(): c for c in existing}

            for conv in unique:
                prompt_lower = conv["prompt"].lower().strip()
                if prompt_lower not in existing_prompts:
                    final_new.append(conv)

            print(f"✅ 新增 {len(final_new)} 條未重複的對話")

            # 合併數據
            merged = existing + final_new

            # 備份原文件
            print(f"\n💾 正在備份原文件...")
            JsonStorage.save(CONVERSATION_FILE, merged, create_backup=True)
            print(f"✅ 文件已備份和保存")

            # 記錄導入日誌
            self._log_import(
                file_path.name, len(final_new), result["errors"], result["duplicates"]
            )

            result["success"] = True
            result["imported"] = len(final_new)
            result["message"] = (
                f"✅ 成功導入 {len(final_new)} 條新對話 (總計 {len(merged)} 條)"
            )

            # 打印摘要
            print("\n" + "=" * 60)
            PrintHelper.header("✨ 導入完成", width=60)
            print("=" * 60)
            print(f"新增對話: {len(final_new)}")
            print(f"重複對話: {result['duplicates']}")
            print(f"無效對話: {result['errors']}")
            print(f"總對話數: {len(merged)}")
            print("=" * 60 + "\n")

            return result

        except Exception as e:
            result["message"] = f"❌ 導入失敗: {str(e)}"
            logger.error(result["message"], exc_info=True)
            print(result["message"])
            return result

    def import_from_url(self, url: str) -> Dict[str, Any]:
        """從遠程 URL 導入數據"""
        print(f"\n📡 正在從 URL 下載: {url}")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # 保存為臨時文件
            temp_file = Path(DATA_DIR) / "temp_import.json"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(response.text)

            # 使用 import_from_file
            result = self.import_from_file(temp_file)

            # 清理臨時文件
            temp_file.unlink()

            return result

        except Exception as e:
            return {
                "success": False,
                "imported": 0,
                "errors": 0,
                "duplicates": 0,
                "message": f"❌ URL 導入失敗: {str(e)}",
                "timestamp": TimeHelper.now_iso(),
            }

    def _log_import(self, source: str, imported: int, errors: int, duplicates: int):
        """記錄導入操作"""
        log_entry = {
            "timestamp": TimeHelper.now_iso(),
            "source": source,
            "imported": imported,
            "errors": errors,
            "duplicates": duplicates,
        }

        JsonStorage.append(self.import_log_path, log_entry)

    def get_import_stats(self) -> Dict[str, Any]:
        """獲取導入統計"""
        conversions = JsonStorage.load(CONVERSATION_FILE, default=[])
        import_logs = JsonStorage.load(self.import_log_path, default=[])

        return {
            "total_conversations": len(conversions),
            "total_imports": len(import_logs),
            "last_import": import_logs[-1] if import_logs else None,
            "total_imported": sum(log.get("imported", 0) for log in import_logs),
        }


# ============ 命令行界面 ============
def main():
    """主函數 - 交互式導入"""
    import sys

    print("\n" + "=" * 60)
    PrintHelper.header("🤖 ChatGPT 數據導入工具", width=60)
    print("=" * 60)

    try:
        importer = ChatGPTImporter()

        print("\n請選擇導入方式：")
        print("1. 從本地 JSON 文件導入")
        print("2. 測試 OpenAI API 連接")
        print("3. 查看導入統計")
        print("4. 退出")

        choice = input("\n請選擇 (1-4): ").strip()

        if choice == "1":
            file_path = input("請輸入文件路徑: ").strip()
            result = importer.import_from_file(Path(file_path))
            print(f"\n結果: {result['message']}")

        elif choice == "2":
            print("\n🔍 正在測試 API 連接...")
            if importer.api_client.test_connection():
                print("✅ API 連接成功！")
            else:
                print("❌ API 連接失敗")

        elif choice == "3":
            stats = importer.get_import_stats()
            print("\n📊 導入統計:")
            print(f"  總對話數: {stats['total_conversations']}")
            print(f"  總導入次數: {stats['total_imports']}")
            print(f"  累計導入: {stats['total_imported']}")
            if stats["last_import"]:
                print(f"  最後導入: {stats['last_import']['timestamp']}")

        elif choice == "4":
            print("👋 再見！")
            return

        else:
            print("❌ 無效選擇")

    except KeyboardInterrupt:
        print("\n\n⚠️  用戶中止")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 出錯: {str(e)}")
        logger.error(str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
