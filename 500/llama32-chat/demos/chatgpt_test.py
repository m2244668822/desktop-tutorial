"""
ChatGPT 本地化測試和驗證工具
驗證導入系統、數據完整性和集成功能
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# 確保可以導入
sys.path.insert(0, str(Path(__file__).parent))

from utils import JsonStorage, PrintHelper, TimeHelper, FileHelper
from constants import CONVERSATION_FILE, LOGS_DIR, DATA_DIR


class ChatGPTLocalizerTest:
    """測試套件"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def header(self, title):
        """打印測試標題"""
        print(f"\n{'=' * 70}")
        print(f"🧪 {title}")
        print(f"{'=' * 70}")

    def test(self, name: str) -> bool:
        """標記測試開始"""
        print(f"\n📋 {name}...", end=" ")
        return True

    def success(self, message: str = ""):
        """標記測試成功"""
        print(f"✅ PASS {message}")
        self.passed += 1

    def fail(self, message: str):
        """標記測試失敗"""
        print(f"❌ FAIL: {message}")
        self.failed += 1

    def warn(self, message: str):
        """標記警告"""
        print(f"⚠️  WARNING: {message}")
        self.warnings += 1

    def run_all_tests(self):
        """運行所有測試"""
        self.header("ChatGPT 本地化系統驗證")

        # 測試 1：文件存在性
        self.test_files_exist()

        # 測試 2：數據有效性
        self.test_data_validity()

        # 測試 3：數據完整性
        self.test_data_integrity()

        # 測試 4：導入日誌
        self.test_import_logs()

        # 測試 5：性能檢查
        self.test_performance()

        # 打印總結
        self.print_summary()

    def test_files_exist(self):
        """測試所需文件是否存在"""
        self.header("文件完整性檢查")

        files_to_check = {
            "對話數據": CONVERSATION_FILE,
            "備份文件": CONVERSATION_FILE.with_suffix(".json.bak"),
            "導入日誌": LOGS_DIR / "import_log.json",
            "模塊文件": Path(__file__).parent / "chatgpt_importer.py",
        }

        for name, path in files_to_check.items():
            self.test(f"檢查 {name}")
            if path.exists():
                size = path.stat().st_size
                self.success(f"({size:,} 字節)")
            else:
                self.fail(f"文件不存在: {path}")

    def test_data_validity(self):
        """測試數據有效性"""
        self.header("數據有效性檢查")

        self.test("加載對話數據")
        conversations = JsonStorage.load(CONVERSATION_FILE, default=[])

        if not conversations:
            self.fail("沒有對話數據")
            return

        self.success(f"({len(conversations)} 條)")

        # 檢查必需字段
        self.test("檢查必需字段")
        required_fields = {"prompt", "response"}
        missing_fields_count = 0

        for i, conv in enumerate(conversations):
            missing = required_fields - set(conv.keys())
            if missing:
                missing_fields_count += 1
                if missing_fields_count <= 3:  # 只顯示前 3 條
                    self.warn(f"第 {i} 條缺少: {missing}")

        if missing_fields_count == 0:
            self.success()
        else:
            self.fail(f"{missing_fields_count} 條記錄缺少必需字段")

        # 檢查數據類型
        self.test("驗證數據類型")
        type_errors = 0

        for i, conv in enumerate(conversations):
            if not isinstance(conv.get("prompt"), str):
                type_errors += 1
            if not isinstance(conv.get("response"), str):
                type_errors += 1

        if type_errors == 0:
            self.success()
        else:
            self.warn(f"發現 {type_errors} 個類型錯誤")

        # 檢查空值
        self.test("檢查空值")
        empty_count = 0

        for i, conv in enumerate(conversations):
            if not conv.get("prompt") or not conv.get("response"):
                empty_count += 1

        if empty_count == 0:
            self.success()
        else:
            self.warn(f"發現 {empty_count} 條空記錄")

    def test_data_integrity(self):
        """測試數據完整性"""
        self.header("數據完整性檢查")

        conversations = JsonStorage.load(CONVERSATION_FILE, default=[])

        if not conversations:
            self.warn("沒有數據可檢查")
            return

        # 檢查唯一性
        self.test("檢查記錄唯一性")
        prompts = [c.get("prompt", "") for c in conversations]
        unique_prompts = len(set(prompts))

        if unique_prompts == len(conversations):
            self.success()
        else:
            duplicates = len(conversations) - unique_prompts
            self.warn(f"發現 {duplicates} 條可能重複的記錄")

        # 檢查時間戳
        self.test("驗證時間戳")
        valid_timestamps = 0

        for conv in conversations:
            timestamp = conv.get("timestamp")
            if timestamp:
                try:
                    TimeHelper.parse_iso(timestamp)
                    valid_timestamps += 1
                except:
                    pass

        if valid_timestamps == len(conversations):
            self.success()
        else:
            self.warn(f"只有 {valid_timestamps}/{len(conversations)} 個有效時間戳")

        # 檢查模型標籤
        self.test("驗證模型標籤")
        models = set(c.get("model", "unknown") for c in conversations)
        self.success(f"(檢測到 {len(models)} 個模型: {', '.join(models)})")

    def test_import_logs(self):
        """測試導入日誌"""
        self.header("導入日誌檢查")

        log_file = LOGS_DIR / "import_log.json"

        self.test("加載導入日誌")
        if not log_file.exists():
            self.warn("導入日誌不存在（初次導入前正常）")
            return

        try:
            with open(log_file, "r") as f:
                content = f.read()
                # 嘗試作為 JSON 數組解析
                try:
                    logs = json.loads(content)
                    if not isinstance(logs, list):
                        logs = [logs]
                except json.JSONDecodeError:
                    # 嘗試作為 JSONL 解析
                    logs = [
                        json.loads(line)
                        for line in content.strip().split("\n")
                        if line.strip()
                    ]

            self.success(f"({len(logs)} 次導入)")

            # 分析導入統計
            self.test("統計導入結果")
            total_imported = sum(log.get("imported", 0) for log in logs)
            total_errors = sum(log.get("errors", 0) for log in logs)
            total_duplicates = sum(log.get("duplicates", 0) for log in logs)

            stats = f"\n  導入記錄: {total_imported}\n"
            stats += f"  錯誤: {total_errors}\n"
            stats += f"  去重: {total_duplicates}"

            self.success(stats)

            # 最後導入時間
            if logs:
                self.test("最後導入時間")
                last = logs[-1].get("timestamp")
                self.success(f"({last})")

        except Exception as e:
            self.fail(f"日誌解析失敗: {str(e)}")

    def test_performance(self):
        """性能檢查"""
        self.header("性能檢查")

        conversations = JsonStorage.load(CONVERSATION_FILE, default=[])

        if not conversations:
            self.warn("沒有數據用於性能測試")
            return

        # 加載時間
        self.test("數據加載時間")
        import time

        start = time.time()
        JsonStorage.load(CONVERSATION_FILE)
        elapsed = time.time() - start

        if elapsed < 1:
            self.success(f"({elapsed * 1000:.2f} ms)")
        else:
            self.warn(f"加載時間過長 ({elapsed:.2f} 秒)")

        # 文件大小
        self.test("文件大小")
        size_mb = CONVERSATION_FILE.stat().st_size / (1024 * 1024)
        self.success(f"({size_mb:.2f} MB)")

        # 平均記錄大小
        self.test("平均記錄大小")
        avg_size = CONVERSATION_FILE.stat().st_size / len(conversations)
        self.success(f"({avg_size:.0f} 字節/記錄)")

        # 數據統計
        self.test("數據統計")
        total_chars = sum(
            len(c.get("prompt", "")) + len(c.get("response", "")) for c in conversations
        )
        avg_prompt = sum(len(c.get("prompt", "")) for c in conversations) / len(
            conversations
        )
        avg_response = sum(len(c.get("response", "")) for c in conversations) / len(
            conversations
        )

        stats = f"\n  總字符數: {total_chars:,}\n"
        stats += f"  平均提示: {avg_prompt:.0f} 字符\n"
        stats += f"  平均回應: {avg_response:.0f} 字符"

        self.success(stats)

    def print_summary(self):
        """打印測試總結"""
        print(f"\n{'=' * 70}")
        print("📊 測試結果總結")
        print(f"{'=' * 70}")
        print(f"✅ 通過: {self.passed}")
        print(f"❌ 失敗: {self.failed}")
        print(f"⚠️  警告: {self.warnings}")

        total = self.passed + self.failed
        if total > 0:
            pass_rate = (self.passed / total) * 100
            print(f"\n通過率: {pass_rate:.1f}%")

        if self.failed == 0:
            print("\n🎉 所有測試通過！系統正常運行。")
        else:
            print(f"\n⚠️  有 {self.failed} 個測試失敗，請檢查上面的詳細信息。")

        print(f"{'=' * 70}\n")


def main():
    """主測試函數"""
    try:
        tester = ChatGPTLocalizerTest()
        tester.run_all_tests()

        # 返回適當的退出碼
        sys.exit(0 if tester.failed == 0 else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  測試被中止")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 測試出錯: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
