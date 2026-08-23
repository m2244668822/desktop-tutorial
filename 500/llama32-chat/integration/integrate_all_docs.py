#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整合所有文檔到 docs_organized/
將 docs/ 裡的所有文件改名並移動到對應分類
"""

import shutil
from pathlib import Path
from typing import Dict, List, Tuple


class DocsIntegrator:
    """文檔整合系統"""

    # docs/ 文件的分類和改名映射
    INTEGRATION_MAP = {
        # 快速開始類
        "快速開始": [
            ("docs/setup/CHATGPT_QUICK_REF.md", "ChatGPT快速參考.md"),
            ("docs/setup/CHATGPT_QUICK_REFERENCE.md", None),  # 重複，忽略
            ("docs/setup/CLAUDE_SETUP.md", "Claude設置指南.md"),
            ("docs/setup/QUICK_REFERENCE.md", "快速參考.md"),
            ("docs/setup/QUICK_START.md", "快速開始.md"),
            ("docs/setup/QUICK_START_MULTI_AGENT.md", "多智能體快速開始.md"),
            ("docs/setup/QUICK_UPDATE.md", "快速更新指南.md"),
        ],
        # 完整指南類
        "完整指南": [
            ("docs/guides/AGENT_GUIDE.md", "智能體指南.md"),
            ("docs/guides/MULTI_AGENT_GUIDE.md", "多智能體指南.md"),
            ("docs/guides/TASK_GUIDE.md", "任務指南.md"),
            ("docs/guides/USAGE_GUIDE.md", "使用指南.md"),
            ("docs/guides/智能體能力說明.md", "智能體能力說明.md"),
            ("docs/guides/自主決策引擎指南.md", "自主決策引擎指南.md"),
            ("docs/setup/FREE_AI_AND_RATE_LIMITING.md", "免費AI與限流說明.md"),
            ("docs/reference/TASK_GUIDE_NEW.md", "任務指南新版.md"),
            ("docs/README.md", "文檔說明.md"),
        ],
        # 架構設計類
        "架構設計": [
            ("docs/setup/RESOURCES_OVERVIEW.md", "資源概覽.md"),
        ],
        # 整合指南類
        "整合指南": [
            ("docs/setup/CHATGPT_IMPORT_GUIDE.md", "ChatGPT導入指南.md"),
            ("docs/setup/CHATGPT_INTEGRATION_GUIDE.md", "ChatGPT整合指南.md"),
            ("docs/setup/CHATGPT_SYSTEM_README.md", "ChatGPT系統說明.md"),
            ("docs/setup/INTEGRATION_GUIDE.md", "整合指南總覽.md"),
            ("docs/DATA_IMPORT_GUIDE.md", "數據導入指南.md"),
        ],
        # 項目完成類
        "項目完成": [
            ("docs/system/COMPLETE_SYSTEM_STATUS.md", "完整系統狀態.md"),
            ("docs/system/UPDATE_SUMMARY.md", "更新摘要.md"),
            ("docs/reference/ERRORS_FIXED.md", "錯誤修復記錄.md"),
            ("docs/reference/PYLANCE_ERRORS.md", "Pylance錯誤記錄.md"),
            ("docs/reference/TASK_SYSTEM_COMPLETE.md", "任務系統完成.md"),
        ],
        # 參考資料類 (新增分類)
        "參考資料": [
            ("docs/reference/DOCS_INDEX.md", "舊版文檔索引.md"),
            ("docs/system/SYSTEM_OVERVIEW.md", "系統總覽舊版.md"),
        ],
    }

    def __init__(self, base_dir: Path = Path(".")):
        self.base_dir = base_dir
        self.docs_organized = base_dir / "docs_organized"
        self.stats = {"moved": 0, "skipped": 0, "errors": 0}

    def integrate_all(self):
        """執行完整整合"""
        print("=" * 70)
        print("📚 整合所有文檔到 docs_organized/")
        print("=" * 70)

        # 1. 創建參考資料分類
        ref_dir = self.docs_organized / "參考資料"
        ref_dir.mkdir(exist_ok=True)
        print(f"\n✓ 創建新分類: 參考資料/")

        # 2. 處理所有文件
        print("\n📦 開始移動和改名文件...")
        for category, files in self.INTEGRATION_MAP.items():
            print(f"\n📁 處理分類: {category}")
            target_dir = self.docs_organized / category

            for old_path_str, new_name in files:
                if new_name is None:  # 標記為重複的文件
                    print(f"   ⊘ 跳過重複文件: {old_path_str}")
                    self.stats["skipped"] += 1
                    continue

                old_path = self.base_dir / old_path_str
                if not old_path.exists():
                    print(f"   ⚠ 文件不存在: {old_path_str}")
                    self.stats["errors"] += 1
                    continue

                # 讀取內容
                try:
                    content = old_path.read_text(encoding="utf-8")

                    # 寫入新位置
                    new_path = target_dir / new_name
                    new_path.write_text(content, encoding="utf-8")

                    print(f"   ✓ {old_path.name} → {new_name}")
                    self.stats["moved"] += 1

                except Exception as e:
                    print(f"   ✗ 錯誤 {old_path.name}: {str(e)}")
                    self.stats["errors"] += 1

        # 3. 更新索引文件
        print("\n📝 更新分類索引...")
        self._update_category_indices()

        # 4. 更新主索引
        print("\n📋 更新主索引...")
        self._update_main_index()

        # 5. 顯示統計
        self._show_stats()

        # 6. 提示後續操作
        self._show_next_steps()

    def _update_category_indices(self):
        """更新每個分類的索引"""
        for category_name in self.INTEGRATION_MAP.keys():
            category_dir = self.docs_organized / category_name
            if not category_dir.exists():
                continue

            # 獲取該分類的所有文件
            md_files = sorted(
                [
                    f
                    for f in category_dir.iterdir()
                    if f.is_file() and f.suffix == ".md" and f.name != "索引.md"
                ]
            )

            # 生成索引內容
            index_content = f"# {category_name}\n\n"
            index_content += f"本分類共有 {len(md_files)} 份文檔。\n\n"
            index_content += "## 文檔列表\n\n"

            for md_file in md_files:
                index_content += f"- [{md_file.stem}]({md_file.name})\n"

            index_content += f"\n\n---\n[返回主索引](../文檔索引.md)\n"

            # 寫入索引
            index_file = category_dir / "索引.md"
            index_file.write_text(index_content, encoding="utf-8")
            print(f"   ✓ 更新: {category_name}/索引.md")

    def _update_main_index(self):
        """更新主索引"""
        all_categories = list(self.INTEGRATION_MAP.keys())

        # 還要包含之前的分類
        existing_categories = [
            "快速開始",
            "完整指南",
            "架構設計",
            "整合指南",
            "項目完成",
            "優化建議",
            "OpenAI數據",
            "參考資料",
        ]

        index_content = "# 📚 完整文檔索引\n\n"
        index_content += "本索引包含所有系統文檔，按類別組織。\n\n"
        index_content += f"更新日期: 2026-02-27\n\n"
        index_content += "---\n\n"

        for category in existing_categories:
            category_dir = self.docs_organized / category
            if not category_dir.exists():
                continue

            md_files = sorted(
                [
                    f
                    for f in category_dir.iterdir()
                    if f.is_file() and f.suffix == ".md" and f.name != "索引.md"
                ]
            )

            index_content += f"## 📁 {category}\n\n"
            index_content += f"共 {len(md_files)} 份文檔\n\n"

            for md_file in md_files:
                index_content += f"- [{md_file.stem}]({category}/{md_file.name})\n"

            index_content += f"\n[查看完整索引]({category}/索引.md)\n\n"
            index_content += "---\n\n"

        # 寫入主索引
        main_index = self.docs_organized / "文檔索引.md"
        main_index.write_text(index_content, encoding="utf-8")
        print("   ✓ 主索引更新完成")

    def _show_stats(self):
        """顯示統計信息"""
        print("\n" + "=" * 70)
        print("📊 整合統計")
        print("=" * 70)
        print(f"✓ 成功移動: {self.stats['moved']} 個文件")
        print(f"⊘ 跳過重複: {self.stats['skipped']} 個文件")
        print(f"✗ 錯誤: {self.stats['errors']} 個文件")
        print("=" * 70)

    def _show_next_steps(self):
        """顯示後續步驟"""
        print("\n" + "=" * 70)
        print("📌 後續步驟")
        print("=" * 70)
        print("\n1️⃣ 確認整合結果:")
        print("   查看 docs_organized/ 資料夾")
        print("\n2️⃣ 備份舊文檔:")
        print("   mv docs docs_backup")
        print("\n3️⃣ 刪除舊文檔 (確認無誤後):")
        print("   rm -rf docs_backup")
        print("\n4️⃣ 查看新索引:")
        print("   cat docs_organized/文檔索引.md")
        print("\n" + "=" * 70)


def main():
    integrator = DocsIntegrator()
    integrator.integrate_all()
    print("\n✨ 整合完成！所有文檔已統一為中文命名並分類整理。\n")


if __name__ == "__main__":
    main()
