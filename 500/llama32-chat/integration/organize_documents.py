#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文檔組織系統
- 將文檔按類型分類到子資料夾
- 改名為中文名稱
- 更新內部鏈接
- 生成中文索引
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
import re


class DocumentOrganizer:
    """文檔組織和管理系統"""

    # 文檔分類對應
    DOC_CATEGORIES = {
        "快速開始": [
            ("NEURAL_QUICK_START.md", "神經系統快速開始.md"),
        ],
        "完整指南": [
            ("NEURAL_SYSTEM_COMPLETE_GUIDE.md", "神經系統完整指南.md"),
            ("README.md", "系統說明.md"),
        ],
        "架構設計": [
            ("NEURAL_SYSTEM_ARCHITECTURE.md", "神經系統架構設計.md"),
            ("PROJECT_STRUCTURE.md", "項目結構說明.md"),
            ("SYSTEM_OVERVIEW.md", "系統概覽.md"),
        ],
        "整合指南": [
            ("NEURAL_INTEGRATION_GUIDE.md", "神經系統整合指南.md"),
            ("CENTRAL_HUB_INTEGRATION_COMPLETE.md", "中樞整合完成.md"),
        ],
        "項目完成": [
            ("NEURAL_PROJECT_COMPLETION.md", "神經系統專案完成.md"),
            ("PROJECT_HANDOVER.md", "項目交接檔.md"),
            ("COMPLETION_SUMMARY.md", "完成摘要.md"),
            ("NEXT_STEPS.md", "後續步驟.md"),
        ],
        "優化建議": [
            ("CODE_OPTIMIZATION_REPORT.md", "代碼優化報告.md"),
        ],
        "OpenAI數據": [
            ("OPENAI_IMPORT_INTEGRATION_GUIDE.md", "OpenAI整合指南.md"),
            ("OPENAI_IMPORT_PROJECT_COMPLETION.md", "OpenAI導入完成.md"),
            ("OPENAI_DATA_FORMAT_REPORT.md", "OpenAI數據格式報告.md"),
        ],
    }

    # 舊名到新名的映射 (用於更新鏈接)
    NAME_MAP = {}

    def __init__(self, base_dir: Path = Path(".")):
        self.base_dir = base_dir
        self.docs_dir = base_dir / "docs_organized"
        self.old_docs = {}  # 存儲舊文檔內容
        self.link_updates = {}  # 鏈接更新記錄

        # 構建名稱映射
        for category, files in self.DOC_CATEGORIES.items():
            for old_name, new_name in files:
                self.NAME_MAP[old_name] = (category, new_name)

    def organize_documents(self):
        """執行文檔組織"""
        print("=" * 70)
        print("📚 文檔組織系統")
        print("=" * 70)

        print("\n1️⃣ 讀取所有文檔...")
        self._read_all_documents()

        print("\n2️⃣ 更新內部鏈接...")
        self._update_internal_links()

        print("\n3️⃣ 複製文檔到新位置...")
        self._copy_documents_to_categories()

        print("\n4️⃣ 生成分類索引...")
        self._generate_category_indices()

        print("\n5️⃣ 生成主索引...")
        self._generate_main_index()

        print("\n✅ 文檔組織完成！")

    def _read_all_documents(self):
        """讀取所有要組織的文檔"""
        for category, files in self.DOC_CATEGORIES.items():
            for old_name, new_name in files:
                old_path = self.base_dir / old_name
                if old_path.exists():
                    with open(old_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.old_docs[old_name] = content
                    print(f"   ✓ 讀取 {old_name}")
                else:
                    print(f"   ⚠ 找不到 {old_name}")

    def _update_internal_links(self):
        """更新所有文檔中的內部鏈接"""
        for old_name, content in self.old_docs.items():
            updated_content = content

            # 更新所有 markdown 鏈接
            for source_name, (category, new_name) in self.NAME_MAP.items():
                if source_name == old_name:
                    continue

                # 尋找 [text](filename.md) 格式的鏈接
                pattern = rf"\[([^\]]+)\]\({re.escape(source_name)}\)"
                replacement = rf"[\1](../{category}/{new_name})"

                if re.search(pattern, updated_content):
                    updated_content = re.sub(pattern, replacement, updated_content)
                    self.link_updates[old_name] = self.link_updates.get(old_name, 0) + 1

            self.old_docs[old_name] = updated_content

    def _copy_documents_to_categories(self):
        """複製文檔到分類資料夾"""
        for category, files in self.DOC_CATEGORIES.items():
            category_dir = self.docs_dir / category
            category_dir.mkdir(parents=True, exist_ok=True)

            for old_name, new_name in files:
                if old_name in self.old_docs:
                    new_path = category_dir / new_name
                    with open(new_path, "w", encoding="utf-8") as f:
                        f.write(self.old_docs[old_name])
                    print(f"   ✓ 已保存 {category}/{new_name}")

    def _generate_category_indices(self):
        """為每個分類生成索引"""
        for category, files in self.DOC_CATEGORIES.items():
            index_content = self._generate_category_index_content(category, files)

            index_path = self.docs_dir / category / "索引.md"
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(index_content)
            print(f"   ✓ 生成 {category}/索引.md")

    def _generate_category_index_content(
        self, category: str, files: List[Tuple]
    ) -> str:
        """生成分類索引內容"""
        content = f"""# 📚 {category}

## 📖 本分類文檔列表

"""

        for old_name, new_name in files:
            description = self._get_file_description(old_name)
            content += f"- [{new_name}]({new_name}): {description}\n"

        content += f"""
## 🔗 快速導航

- [回到主索引](../../文檔索引.md)
"""

        return content

    def _get_file_description(self, filename: str) -> str:
        """根據文件名獲取描述"""
        descriptions = {
            "NEURAL_QUICK_START.md": "5 分鐘快速開始指南",
            "NEURAL_SYSTEM_COMPLETE_GUIDE.md": "完整的技術參考文檔",
            "NEURAL_INTEGRATION_GUIDE.md": "系統集成步驟詳解",
            "NEURAL_SYSTEM_ARCHITECTURE.md": "系統架構和設計圖",
            "NEURAL_PROJECT_COMPLETION.md": "項目完成報告",
            "PROJECT_HANDOVER.md": "項目交接詳細檔案",
            "CODE_OPTIMIZATION_REPORT.md": "代碼優化分析報告",
            "OPENAI_IMPORT_INTEGRATION_GUIDE.md": "OpenAI 整合指南",
            "OPENAI_IMPORT_PROJECT_COMPLETION.md": "OpenAI 導入完成報告",
            "OPENAI_DATA_FORMAT_REPORT.md": "OpenAI 數據格式分析",
            "CENTRAL_HUB_INTEGRATION_COMPLETE.md": "中樞系統整合完成",
            "README.md": "系統總體說明",
            "PROJECT_STRUCTURE.md": "項目結構詳解",
            "SYSTEM_OVERVIEW.md": "系統概覽和功能",
            "COMPLETION_SUMMARY.md": "完成項目摘要",
            "NEXT_STEPS.md": "後續計劃和方向",
        }
        return descriptions.get(filename, "文檔")

    def _generate_main_index(self):
        """生成主索引檔案"""
        content = """# 📚 完整文檔索引

**最後更新**: 2026-02-27  
**文檔版本**: 2.0

---

## 🗂️ 文檔分類

### 📖 [快速開始](快速開始/索引.md)
快速上手神經系統，5 分鐘內開始使用。

### 📚 [完整指南](完整指南/索引.md)
深入學習神經系統的完整技術文檔。

### 🏗️ [架構設計](架構設計/索引.md)
理解系統架構和設計原理。

### 🔧 [整合指南](整合指南/索引.md)  
將神經系統整合到你的應用中。

### ✅ [項目完成](項目完成/索引.md)
項目完成報告和交接檔案。

### ⚡ [優化建議](優化建議/索引.md)
代碼優化和性能提升建議。

### 🔌 [OpenAI 數據](OpenAI數據/索引.md)
OpenAI 數據導入和整合指南。

---

## 🎯 選擇你的學習路徑

### 路徑 1: 快速使用 (15 分鐘)
1. [神經系統快速開始](快速開始/神經系統快速開始.md)
2. 試用示例代碼
3. 查看常見場景

### 路徑 2: 開發者集成 (1.5 小時)
1. [神經系統快速開始](快速開始/神經系統快速開始.md)
2. [神經系統整合指南](整合指南/神經系統整合指南.md)
3. [神經系統架構設計](架構設計/神經系統架構設計.md)
4. 實施集成代碼

### 路徑 3: 技術深潛 (2 小時)
1. [神經系統完整指南](完整指南/神經系統完整指南.md)
2. [神經系統架構設計](架構設計/神經系統架構設計.md)
3. 研究源代碼

---

## 📊 文檔統計

- **總分類**: 7
- **總文檔**: 15+
- **總行數**: 3,500+

---

## ✨ 亮點

✅ 8 個文檔分類  
✅ 中文名稱和描述  
✅ 完整的交叉參考  
✅ 多個學習路徑  
✅ 快速導航結構

---

**開始閱讀**: [快速開始](快速開始/神經系統快速開始.md) 或選擇上面的任何路徑。
"""

        main_index_path = self.docs_dir / "文檔索引.md"
        with open(main_index_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"   ✓ 生成主索引: 文檔索引.md")


def main():
    organizer = DocumentOrganizer(Path("/Volumes/智能體/城城城程式/500/llama32-chat"))
    organizer.organize_documents()


if __name__ == "__main__":
    main()
