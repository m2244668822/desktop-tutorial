#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台申請自動追蹤系統 (Platform Application Tracker)

功能：
1. 自動追蹤多平台申請狀態
2. 提醒後續跟進時間
3. 記錄申請進度與反饋
4. 生成申請進度報告
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class PlatformApplication:
    """平台申請記錄"""

    platform_id: str  # appen, remotasks, lionbridge, clickworker
    platform_name: str  # 平台名稱
    application_date: str  # 申請日期 (ISO format)
    status: str  # pending, approved, rejected, in_progress
    email_used: str  # 使用的郵箱
    notes: str = ""  # 備註
    first_followup_date: Optional[str] = None  # 首次跟進日期
    latest_update: Optional[str] = None  # 最後更新日期
    expected_approval_days: int = 14  # 預期審核天數
    documents_submitted: List[str] = None  # 提交的文件列表

    def __post_init__(self):
        if self.documents_submitted is None:
            self.documents_submitted = []


class PlatformApplicationTracker:
    """平台申請追蹤器"""

    PLATFORMS = {
        "appen": {
            "name": "Appen",
            "url": "https://appen.com/join-our-crowd/",
            "expected_days": 7,
            "priority": "high",
        },
        "lionbridge": {
            "name": "Lionbridge AI",
            "url": "https://www.lionbridge.com/join-our-team/",
            "expected_days": 10,
            "priority": "high",
        },
        "clickworker": {
            "name": "Clickworker",
            "url": "https://www.clickworker.com",
            "expected_days": 3,
            "priority": "medium",
        },
        "remotasks": {
            "name": "Remotasks",
            "url": "https://www.remotasks.com",
            "expected_days": 7,
            "priority": "high",
        },
        "mturk": {
            "name": "Amazon MTurk",
            "url": "https://www.mturk.com",
            "expected_days": 14,
            "priority": "low",
        },
    }

    def __init__(self, tracker_dir: str = "data/platform_applications"):
        self.tracker_dir = Path(tracker_dir)
        self.tracker_dir.mkdir(parents=True, exist_ok=True)

        self.tracker_file = self.tracker_dir / "applications.json"
        self.applications = self._load_applications()

    def submit_application(
        self, platform_id: str, email: str, notes: str = ""
    ) -> Dict[str, Any]:
        """
        記錄新的平台申請

        Args:
            platform_id: 平台ID (appen, remotasks, etc.)
            email: 使用的郵箱
            notes: 額外備註

        Returns:
            申請記錄
        """
        if platform_id not in self.PLATFORMS:
            raise ValueError(f"Unknown platform: {platform_id}")

        platform_info = self.PLATFORMS[platform_id]

        app = PlatformApplication(
            platform_id=platform_id,
            platform_name=platform_info["name"],
            application_date=datetime.now().isoformat(),
            status="pending",
            email_used=email,
            notes=notes,
            expected_approval_days=platform_info["expected_days"],
            documents_submitted=["resume", "cover_letter"],
        )

        self.applications.append(asdict(app))
        self._save_applications()

        return asdict(app)

    def update_status(
        self, platform_id: str, status: str, notes: str = ""
    ) -> Dict[str, Any]:
        """更新申請狀態"""
        for app in self.applications:
            if app["platform_id"] == platform_id:
                app["status"] = status
                app["latest_update"] = datetime.now().isoformat()
                if notes:
                    app["notes"] = notes
                self._save_applications()
                return app

        raise ValueError(f"Application not found for platform: {platform_id}")

    def get_followup_reminders(self) -> List[Dict[str, Any]]:
        """
        獲取需要跟進的申請

        Returns:
            需要跟進的申請列表
        """
        reminders = []
        now = datetime.now()

        for app in self.applications:
            if app["status"] == "pending":
                app_date = datetime.fromisoformat(app["application_date"])
                expected_approval = app_date + timedelta(
                    days=app["expected_approval_days"]
                )

                # 如果未審核且時間已過預期，需要跟進
                if now > expected_approval:
                    days_overdue = (now - expected_approval).days
                    reminders.append(
                        {
                            "platform": app["platform_name"],
                            "days_overdue": days_overdue,
                            "email": app["email_used"],
                            "action": f"Send follow-up email after {days_overdue} days",
                            "priority": "high" if days_overdue > 7 else "medium",
                        }
                    )

        return reminders

    def get_status_summary(self) -> Dict[str, Any]:
        """獲取申請狀態總結"""
        summary = {
            "total_applications": len(self.applications),
            "by_status": {"pending": 0, "approved": 0, "rejected": 0, "in_progress": 0},
            "by_priority": {"high": 0, "medium": 0, "low": 0},
            "applications": [],
        }

        for app in self.applications:
            status = app["status"]
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1

            platform_id = app["platform_id"]
            priority = self.PLATFORMS.get(platform_id, {}).get("priority", "low")
            summary["by_priority"][priority] += 1

            summary["applications"].append(
                {
                    "platform": app["platform_name"],
                    "status": app["status"],
                    "date": app["application_date"][:10],  # 只取日期部分
                    "days_elapsed": (
                        datetime.now() - datetime.fromisoformat(app["application_date"])
                    ).days,
                }
            )

        return summary

    def generate_followup_template(self, platform_id: str) -> str:
        """生成跟進郵件範本"""
        platform = self.PLATFORMS.get(platform_id, {})

        template = f"""Subject: Follow-up on Data Annotation Application

Dear {platform.get("name")} Team,

I am writing to follow up on my data annotation application submitted on [DATE]. 
I remain very interested in contributing to your AI training projects and would 
appreciate any updates on my application status.

I am available for 10-20 hours per week and committed to providing high-quality work.

Thank you for your consideration.

Best regards,
Pin-Yu Chen
m2244668822@gmail.com
Taiwan"""

        return template

    def _load_applications(self) -> List[Dict[str, Any]]:
        """加載申請記錄"""
        if self.tracker_file.exists():
            with open(self.tracker_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_applications(self):
        """保存申請記錄"""
        with open(self.tracker_file, "w", encoding="utf-8") as f:
            json.dump(self.applications, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 使用示例
    tracker = PlatformApplicationTracker()

    # 記錄新申請
    print("📝 平台申請追蹤系統")
    print("=" * 60)

    # 模擬提交申請
    platforms_to_apply = ["appen", "lionbridge", "clickworker"]

    for platform_id in platforms_to_apply:
        try:
            app = tracker.submit_application(
                platform_id=platform_id,
                email="m2244668822@gmail.com",
                notes="Submitted with updated resume emphasizing mental health background",
            )
            print(f"\n✅ {app['platform_name']} 申請已記錄")
            print(f"   申請日期: {app['application_date'][:10]}")
            print(f"   預期審核: {app['expected_approval_days']} 天")
        except ValueError as e:
            print(f"❌ {platform_id}: {e}")

    # 獲取狀態總結
    print("\n" + "-" * 60)
    summary = tracker.get_status_summary()
    print(f"\n📊 申請狀態總結:")
    print(f"   總申請數: {summary['total_applications']}")
    print(f"   待審: {summary['by_status']['pending']}")
    print(f"   已批准: {summary['by_status']['approved']}")
    print(f"   已拒絕: {summary['by_status']['rejected']}")

    # 檢查需要跟進的申請
    reminders = tracker.get_followup_reminders()
    if reminders:
        print(f"\n⚠️  需要跟進的申請: {len(reminders)}")
        for reminder in reminders:
            print(f"   • {reminder['platform']}: {reminder['days_overdue']} 天未審")
    else:
        print(f"\n✅ 暫無需要跟進的申請")

    print("\n" + "=" * 60)
