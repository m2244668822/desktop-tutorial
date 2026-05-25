#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

# 設定根目錄
BASE_DIR = Path(__file__).parent.parent.parent.parent


def move_files(pattern, target_subfolder):
    target_dir = BASE_DIR / target_subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    # 遍歷主目錄下的檔案 (不遞迴，避免弄亂子目錄)
    for file_path in BASE_DIR.glob(pattern):
        if file_path.is_file():
            # 排除腳本本身和關鍵配置
            if file_path.name in ["README.md", "GEMINI.md", ".gitignore"]:
                continue

            try:
                shutil.move(str(file_path), str(target_dir / file_path.name))
                count += 1
            except Exception as e:
                print(f"無法移動 {file_path.name}: {e}")
    return count


def clean_caches():
    count = 0
    for cache_dir in ["__pycache__", ".ruff_cache", ".pytest_cache"]:
        for path in BASE_DIR.rglob(cache_dir):
            if path.is_dir():
                try:
                    shutil.rmtree(path)
                    count += 1
                except Exception as e:
                    print(f"無法刪除快取 {path}: {e}")
    return count


def organize():
    print("🧹 工作區管家正在開始清掃...")

    # 1. 整理報告
    report_count = move_files("*REPORT*.md", "reports")
    status_count = move_files("*STATUS*.md", "reports")
    summary_count = move_files("*SUMMARY*.md", "reports")

    # 2. 整理歷史檔案 (帶日期的 .md)
    # 匹配模式如: 2026-03-07
    history_count = move_files("*2026-[0-9][0-9]-[0-9][0-9]*", "archive")

    # 3. 整理備份檔
    backup_count = move_files("*.bak", "archive/backups")
    backup_count += move_files("*.backup*", "archive/backups")

    # 4. 清理快取
    cache_count = clean_caches()

    print("\n--- 清掃完成報告 ---")
    print(
        f"📝 報告類檔案: {report_count + status_count + summary_count} 個 -> reports/"
    )
    print(f"📦 歷史紀錄: {history_count} 個 -> archive/")
    print(f"💾 備份檔案: {backup_count} 個 -> archive/backups/")
    print(f"⚡ 清理快取目錄: {cache_count} 個")
    print("--------------------")


if __name__ == "__main__":
    organize()
