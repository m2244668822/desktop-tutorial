#!/usr/bin/env python3
"""Remotasks 自動週報生成器 - 支援 Markdown 和 CSV 格式"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any


class RemotasksReportGenerator:
    def __init__(self, revenue_log_path: Path):
        self.revenue_log_path = revenue_log_path

    def _load_entries(self) -> List[Dict[str, Any]]:
        """讀取收益記錄"""
        if not self.revenue_log_path.exists():
            return []
        with self.revenue_log_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _filter_by_date_range(
        self, entries: List[Dict[str, Any]], days: int
    ) -> List[Dict[str, Any]]:
        """按日期範圍過濾記錄"""
        if not entries:
            return []

        cutoff_date = datetime.now() - timedelta(days=days)
        filtered = []

        for entry in entries:
            try:
                entry_date = datetime.fromisoformat(entry.get("recorded_at", ""))
                if entry_date >= cutoff_date:
                    filtered.append(entry)
            except (ValueError, TypeError):
                continue

        return filtered

    def generate_daily_report_md(self, output_path: Path) -> str:
        """生成每日報告（Markdown 格式）"""
        entries = self._load_entries()
        today_entries = self._filter_by_date_range(entries, days=1)

        total_hours = sum(float(e.get("hours", 0)) for e in today_entries)
        total_usd = sum(float(e.get("amount_usd", 0)) for e in today_entries)
        avg_hourly = total_usd / total_hours if total_hours > 0 else 0

        # 按類別分組
        by_category: Dict[str, Dict[str, float]] = {}
        for entry in today_entries:
            cat = entry.get("category", "未分類")
            if cat not in by_category:
                by_category[cat] = {"hours": 0.0, "amount": 0.0, "count": 0}
            by_category[cat]["hours"] += float(entry.get("hours", 0))
            by_category[cat]["amount"] += float(entry.get("amount_usd", 0))
            by_category[cat]["count"] += 1

        # 生成 Markdown
        md_content = f"""# Remotasks 每日收益報告

**日期**: {datetime.now().strftime("%Y年%m月%d日")}  
**記錄時間**: {datetime.now().strftime("%H:%M:%S")}

---

## 📊 今日摘要

| 指標 | 數值 |
|------|------|
| 完成任務數 | {len(today_entries)} |
| 總工時 | {total_hours:.2f} 小時 |
| 總收益 | ${total_usd:.2f} USD |
| 平均時薪 | ${avg_hourly:.2f} USD/h |

---

## 📋 按類別統計

"""
        if by_category:
            md_content += "| 類別 | 任務數 | 工時 | 收益 | 時薪 |\n"
            md_content += "|------|--------|------|------|------|\n"
            for cat, stats in sorted(by_category.items()):
                cat_hourly = (
                    stats["amount"] / stats["hours"] if stats["hours"] > 0 else 0
                )
                md_content += (
                    f"| {cat} | {stats['count']} | "
                    f"{stats['hours']:.2f}h | "
                    f"${stats['amount']:.2f} | "
                    f"${cat_hourly:.2f}/h |\n"
                )
        else:
            md_content += "*今日無記錄*\n"

        md_content += "\n---\n\n## 📝 詳細記錄\n\n"

        if today_entries:
            for i, entry in enumerate(today_entries, 1):
                status_emoji = "✅" if entry.get("status") == "paid" else "⏳"
                md_content += f"""
### {i}. {entry.get("task_id", "N/A")} {status_emoji}

- **類別**: {entry.get("category", "未分類")}
- **工時**: {entry.get("hours", 0)} 小時
- **收益**: ${entry.get("amount_usd", 0)} USD
- **狀態**: {entry.get("status", "pending")}
- **記錄時間**: {entry.get("recorded_at", "N/A")}
- **備註**: {entry.get("note", "無")}
"""
        else:
            md_content += "*今日無記錄*\n"

        md_content += f"\n---\n\n*報告生成時間: {datetime.now().isoformat()}*\n"

        # 寫入檔案
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_content, encoding="utf-8")

        return md_content

    def generate_weekly_report_md(self, output_path: Path) -> str:
        """生成每週報告（Markdown 格式）"""
        entries = self._load_entries()
        week_entries = self._filter_by_date_range(entries, days=7)

        total_hours = sum(float(e.get("hours", 0)) for e in week_entries)
        total_usd = sum(float(e.get("amount_usd", 0)) for e in week_entries)
        paid_usd = sum(
            float(e.get("amount_usd", 0))
            for e in week_entries
            if e.get("status") == "paid"
        )
        pending_usd = total_usd - paid_usd
        avg_hourly = total_usd / total_hours if total_hours > 0 else 0

        # 按類別分組
        by_category: Dict[str, Dict[str, float]] = {}
        for entry in week_entries:
            cat = entry.get("category", "未分類")
            if cat not in by_category:
                by_category[cat] = {"hours": 0.0, "amount": 0.0, "count": 0}
            by_category[cat]["hours"] += float(entry.get("hours", 0))
            by_category[cat]["amount"] += float(entry.get("amount_usd", 0))
            by_category[cat]["count"] += 1

        # 按日分組
        by_date: Dict[str, Dict[str, float]] = {}
        for entry in week_entries:
            try:
                date_str = entry.get("recorded_at", "")[:10]
                if date_str not in by_date:
                    by_date[date_str] = {"hours": 0.0, "amount": 0.0, "count": 0}
                by_date[date_str]["hours"] += float(entry.get("hours", 0))
                by_date[date_str]["amount"] += float(entry.get("amount_usd", 0))
                by_date[date_str]["count"] += 1
            except (ValueError, TypeError, IndexError):
                continue

        # 生成 Markdown
        md_content = f"""# Remotasks 每週收益報告

**日期範圍**: 過去 7 天  
**報告生成**: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}

---

## 📊 週度摘要

| 指標 | 數值 |
|------|------|
| 完成任務數 | {len(week_entries)} |
| 總工時 | {total_hours:.2f} 小時 |
| 總收益 | ${total_usd:.2f} USD |
| 已付款 | ${paid_usd:.2f} USD |
| 待付款 | ${pending_usd:.2f} USD |
| 平均時薪 | ${avg_hourly:.2f} USD/h |
| 日均工時 | {total_hours / 7:.2f} 小時/天 |
| 日均收益 | ${total_usd / 7:.2f} USD/天 |

---

## 📋 按類別統計

"""
        if by_category:
            md_content += "| 類別 | 任務數 | 工時 | 收益 | 佔比 | 時薪 |\n"
            md_content += "|------|--------|------|------|------|------|\n"
            for cat, stats in sorted(
                by_category.items(), key=lambda x: x[1]["amount"], reverse=True
            ):
                cat_hourly = (
                    stats["amount"] / stats["hours"] if stats["hours"] > 0 else 0
                )
                percentage = (stats["amount"] / total_usd * 100) if total_usd > 0 else 0
                md_content += (
                    f"| {cat} | {stats['count']} | "
                    f"{stats['hours']:.2f}h | "
                    f"${stats['amount']:.2f} | "
                    f"{percentage:.1f}% | "
                    f"${cat_hourly:.2f}/h |\n"
                )
        else:
            md_content += "*本週無記錄*\n"

        md_content += "\n---\n\n## 📅 每日趨勢\n\n"

        if by_date:
            md_content += "| 日期 | 任務數 | 工時 | 收益 |\n"
            md_content += "|------|--------|------|------|\n"
            for date_str, stats in sorted(by_date.items()):
                md_content += (
                    f"| {date_str} | {stats['count']} | "
                    f"{stats['hours']:.2f}h | ${stats['amount']:.2f} |\n"
                )
        else:
            md_content += "*本週無記錄*\n"

        md_content += f"\n---\n\n*報告生成時間: {datetime.now().isoformat()}*\n"

        # 寫入檔案
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_content, encoding="utf-8")

        return md_content

    def generate_csv_export(self, output_path: Path, days: int = 30) -> int:
        """導出為 CSV 格式（可用於 Excel 分析）"""
        entries = self._load_entries()
        filtered_entries = self._filter_by_date_range(entries, days=days)

        if not filtered_entries:
            return 0

        # 寫入 CSV
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8-sig") as csvfile:
            fieldnames = [
                "recorded_at",
                "task_id",
                "category",
                "hours",
                "amount_usd",
                "status",
                "note",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for entry in filtered_entries:
                writer.writerow(
                    {
                        "recorded_at": entry.get("recorded_at", ""),
                        "task_id": entry.get("task_id", ""),
                        "category": entry.get("category", ""),
                        "hours": entry.get("hours", 0),
                        "amount_usd": entry.get("amount_usd", 0),
                        "status": entry.get("status", ""),
                        "note": entry.get("note", ""),
                    }
                )

        return len(filtered_entries)


# CLI 介面
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Remotasks 報告生成器")
    parser.add_argument(
        "--type", choices=["daily", "weekly", "csv"], required=True, help="報告類型"
    )
    parser.add_argument(
        "--output", type=Path, help="輸出路徑（預設：reports/[日期]_report.[md|csv]）"
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/remotasks/revenue_log.json"),
        help="收益記錄 JSON 路徑",
    )
    parser.add_argument(
        "--days", type=int, default=30, help="CSV 導出天數（預設 30 天）"
    )

    args = parser.parse_args()

    generator = RemotasksReportGenerator(args.data)

    if args.type == "daily":
        output = args.output or Path(
            f"reports/remotasks_{datetime.now().strftime('%Y%m%d')}_daily.md"
        )
        content = generator.generate_daily_report_md(output)
        print(f"✅ 每日報告已生成: {output}")
        print(f"   預覽前 10 行:")
        print("\n".join(content.split("\n")[:10]))

    elif args.type == "weekly":
        output = args.output or Path(
            f"reports/remotasks_{datetime.now().strftime('%Y%m%d')}_weekly.md"
        )
        content = generator.generate_weekly_report_md(output)
        print(f"✅ 每週報告已生成: {output}")
        print(f"   預覽前 10 行:")
        print("\n".join(content.split("\n")[:10]))

    elif args.type == "csv":
        output = args.output or Path(
            f"reports/remotasks_{datetime.now().strftime('%Y%m%d')}_export.csv"
        )
        count = generator.generate_csv_export(output, days=args.days)
        print(f"✅ CSV 已導出: {output}")
        print(f"   記錄數: {count} 筆（過去 {args.days} 天）")
