#!/usr/bin/env python3
"""Emit a privacy-safe, machine-readable Trevor training readiness report."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent


def _path_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "files": 0, "size_bytes": 0, "latest_mtime": ""}
    files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
    latest = max((item.stat().st_mtime for item in files), default=0.0)
    return {
        "exists": True,
        "files": len(files),
        "size_bytes": sum(item.stat().st_size for item in files),
        "latest_mtime": datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()
        if latest
        else "",
    }


def collect_git_info(repo_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()

    status = run("status", "--porcelain")
    counts = run("rev-list", "--left-right", "--count", "HEAD...origin/main")
    ahead = behind = 0
    try:
        ahead, behind = (int(value) for value in counts.split())
    except (ValueError, TypeError):
        pass
    return {
        "branch": run("branch", "--show-current"),
        "dirty_files": [line[3:] for line in status.splitlines() if line.strip()],
        "ahead_origin_main": ahead,
        "behind_origin_main": behind,
    }


def collect_backup_status(backup_root: Path) -> dict[str, Any]:
    manifests = sorted(backup_root.rglob("*.manifest.json")) if backup_root.exists() else []
    if not manifests:
        return {"available": False, "verified": False, "manifest": "", "snapshot": ""}
    manifest_path = max(manifests, key=lambda item: item.stat().st_mtime)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"available": True, "verified": False, "manifest": str(manifest_path), "snapshot": ""}
    snapshot_path = manifest_path.with_name(
        manifest_path.name.replace(".manifest.json", ".trevor.enc")
    )
    size_ok = snapshot_path.exists() and snapshot_path.stat().st_size == int(
        payload.get("snapshot_size", -1) or -1
    )
    manifest_ok = bool(payload.get("snapshot_sha256") and payload.get("archive_sha256"))
    return {
        "available": True,
        "verified": bool(size_ok and manifest_ok),
        "manifest": str(manifest_path),
        "snapshot": str(snapshot_path),
        "snapshot_size": snapshot_path.stat().st_size if snapshot_path.exists() else 0,
        "manifest_file_count": int(payload.get("file_count", 0) or 0),
        "snapshot_sha256": str(payload.get("snapshot_sha256", "")),
    }


def collect_retrieval_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "cases": 0, "hit_rate": 0.0, "mrr": 0.0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"available": False, "cases": 0, "hit_rate": 0.0, "mrr": 0.0}
    metrics = payload.get("metrics", {}) if isinstance(payload, dict) else {}
    return {
        "available": True,
        "cases": int(payload.get("cases", 0) or 0),
        "hit_rate": float(metrics.get("hit_rate", payload.get("hit_rate", 0.0)) or 0.0),
        "mrr": float(metrics.get("mrr", payload.get("mrr", 0.0)) or 0.0),
        "citation_correctness": float(metrics.get("citation_correctness", 0.0) or 0.0),
        "privacy_leakage": int(metrics.get("privacy_leakage", 0) or 0),
        "no_hit_false_positive": int(
            (metrics.get("no_hit", {}) or {}).get("false_positive", 0) or 0
        ),
        "stale_retrieved": int(
            (metrics.get("stale", {}) or {}).get("retrieved", 0) or 0
        ),
    }


def _training_summary_zh(
    readiness: dict[str, bool], retrieval: dict[str, Any], backup: dict[str, Any], git: dict[str, Any]
) -> str:
    labels = {
        "data": "資料",
        "retrieval": "檢索",
        "backup": "備份",
        "git": "Git",
    }
    missing = [labels[key] for key, ok in readiness.items() if not ok]
    if not missing:
        return (
            "訓練準備狀態：可交付。資料、檢索、備份與 Git 都已通過；"
            f"目前檢索 hit rate 為 {retrieval.get('hit_rate', 0.0):.4f}。"
        )
    return f"訓練準備狀態：尚未可交付；待處理層級：{'、'.join(missing)}。"


def build_training_status_report(
    *,
    repo_root: str | Path,
    data_root: str | Path,
    backup_root: str | Path,
    retrieval_report: str | Path,
    git_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = {"root": str(data_root), **_path_stats(Path(data_root))}
    retrieval = collect_retrieval_status(Path(retrieval_report))
    backup = collect_backup_status(Path(backup_root))
    git = git_info or collect_git_info(Path(repo_root))
    readiness = {
        "data": bool(data["exists"] and data["files"] > 0),
        "retrieval": bool(
            retrieval.get("available")
            and retrieval.get("cases", 0) >= 30
            and retrieval.get("hit_rate", 0.0) >= 0.75
            and retrieval.get("privacy_leakage", 1) == 0
        ),
        "backup": bool(backup.get("available") and backup.get("verified")),
        "git": not bool(git.get("dirty_files")),
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intro_zh": "中文說明：這份報告用來確認智能體訓練的資料、檢索、備份與版本狀態。",
        "summary_zh": _training_summary_zh(readiness, retrieval, backup, git),
        "field_descriptions_zh": {
            "readiness": "四個必要層級是否通過：data、retrieval、backup、git。",
            "retrieval": "檢索命中率、排名、引用正確性與 stale／隱私風險。",
            "backup": "最近一次加密 snapshot 與 manifest 是否通過校驗。",
            "git": "目前工作樹是否乾淨，以及與遠端分支的差異。",
        },
        "readiness": readiness,
        "git": git,
        "data": data,
        "retrieval": retrieval,
        "backup": backup,
        "notes": [
            "只輸出檔案統計、索引指標、備份校驗欄位與 Git 狀態；不輸出對話內容、API key 或加密金鑰。",
            "retrieval hit_rate/MRR 只計入預期命中的正向案例；no-hit、conflict、stale 另列。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=BASE_DIR)
    parser.add_argument("--data-root", type=Path, default=Path("TrevorData"))
    parser.add_argument("--backup-root", type=Path, default=Path("TrevorBackups"))
    parser.add_argument(
        "--retrieval-report",
        type=Path,
        default=Path("TrevorData/knowledge_hub/reports/retrieval_eval_latest.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_training_status_report(
        repo_root=args.repo,
        data_root=args.data_root,
        backup_root=args.backup_root,
        retrieval_report=args.retrieval_report,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if all(report["readiness"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
