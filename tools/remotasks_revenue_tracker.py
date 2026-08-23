#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List


DEFAULT_DB_PATH = Path("data/remotasks/revenue_log.json")


@dataclass
class RevenueEntry:
    task_id: str
    category: str
    hours: float
    amount_usd: float
    status: str
    recorded_at: str
    note: str = ""


class RemotasksRevenueTracker:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self._write([])

    def _read(self) -> List[dict]:
        with self.db_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: List[dict]) -> None:
        with self.db_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_entry(
        self,
        task_id: str,
        category: str,
        hours: float,
        amount_usd: float,
        status: str,
        note: str,
    ) -> RevenueEntry:
        entry = RevenueEntry(
            task_id=task_id,
            category=category,
            hours=hours,
            amount_usd=amount_usd,
            status=status,
            recorded_at=datetime.now().isoformat(timespec="seconds"),
            note=note,
        )

        data = self._read()
        data.append(asdict(entry))
        self._write(data)
        return entry

    def list_entries(self, limit: int = 20) -> List[dict]:
        data = self._read()
        return list(reversed(data[-limit:]))

    def summary(self) -> dict:
        data = self._read()
        if not data:
            return {
                "count": 0,
                "total_hours": 0.0,
                "total_amount_usd": 0.0,
                "avg_hourly_usd": 0.0,
                "paid_amount_usd": 0.0,
                "pending_amount_usd": 0.0,
            }

        total_hours = sum(float(item.get("hours", 0.0)) for item in data)
        total_amount_usd = sum(float(item.get("amount_usd", 0.0)) for item in data)
        paid_amount_usd = sum(
            float(item.get("amount_usd", 0.0))
            for item in data
            if str(item.get("status", "")).lower() == "paid"
        )
        pending_amount_usd = total_amount_usd - paid_amount_usd

        return {
            "count": len(data),
            "total_hours": round(total_hours, 2),
            "total_amount_usd": round(total_amount_usd, 2),
            "avg_hourly_usd": round(total_amount_usd / total_hours, 2)
            if total_hours
            else 0.0,
            "paid_amount_usd": round(paid_amount_usd, 2),
            "pending_amount_usd": round(pending_amount_usd, 2),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remotasks 收益追蹤工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="新增一筆收益記錄")
    add_parser.add_argument("--task-id", required=True, help="Remotasks 任務 ID")
    add_parser.add_argument(
        "--category", required=True, help="任務類別，例如：image_annotation"
    )
    add_parser.add_argument("--hours", required=True, type=float, help="本次投入時數")
    add_parser.add_argument(
        "--amount-usd", required=True, type=float, help="本次收益（美元）"
    )
    add_parser.add_argument(
        "--status",
        default="pending",
        choices=["pending", "paid"],
        help="款項狀態",
    )
    add_parser.add_argument("--note", default="", help="備註")

    list_parser = subparsers.add_parser("list", help="顯示最近記錄")
    list_parser.add_argument("--limit", default=20, type=int, help="顯示筆數")

    subparsers.add_parser("summary", help="顯示收益摘要")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    tracker = RemotasksRevenueTracker()

    if args.command == "add":
        entry = tracker.add_entry(
            task_id=args.task_id,
            category=args.category,
            hours=args.hours,
            amount_usd=args.amount_usd,
            status=args.status,
            note=args.note,
        )
        print("✅ 已新增收益記錄")
        print(json.dumps(asdict(entry), ensure_ascii=False, indent=2))
        return

    if args.command == "list":
        entries = tracker.list_entries(limit=args.limit)
        print(f"📄 最近 {len(entries)} 筆")
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return

    if args.command == "summary":
        stats = tracker.summary()
        print("📊 收益摘要")
        print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
