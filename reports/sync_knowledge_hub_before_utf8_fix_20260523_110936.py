#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
統一知識中樞同步器。

用途：
1. 將 docs / reports / logs / opai 本地導出 / local_knowledge 收斂到單一入口
2. 保留原始路徑，避免打斷現有腳本與硬編碼引用
3. 生成 manifest 供桌面端與記憶層查詢
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
HUB_DIR = BASE_DIR / "data" / "knowledge_hub"
SOURCE_MAP = {
    "docs": BASE_DIR / "docs",
    "reports": BASE_DIR / "reports",
    "logs": BASE_DIR / "logs",
    "chatgpt_export": BASE_DIR / "本地" / "opai本地",
    "local_knowledge": BASE_DIR / "500" / "llama32-chat" / "data" / "local_knowledge",
}


def path_stats(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "files": 0, "size_bytes": 0, "latest_mtime": None}

    files = [p for p in path.rglob("*") if p.is_file()]
    latest_mtime = max((p.stat().st_mtime for p in files), default=0)
    return {
        "exists": True,
        "files": len(files),
        "size_bytes": sum(p.stat().st_size for p in files),
        "latest_mtime": datetime.fromtimestamp(latest_mtime).isoformat()
        if latest_mtime
        else None,
    }


def ensure_symlink(name: str, target: Path) -> None:
    link_path = HUB_DIR / name
    relative_target = Path(os.path.relpath(target, HUB_DIR))

    if link_path.is_symlink():
        if link_path.resolve() == target.resolve():
            return
        link_path.unlink()
    elif link_path.exists():
        return

    link_path.symlink_to(relative_target, target_is_directory=True)


def build_manifest() -> dict:
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "hub_dir": str(HUB_DIR),
        "sources": {},
        "notes": [
            "本中樞使用符號連結保留原始路徑，避免破壞既有程式引用。",
            "ChatGPT 本地導出以 本地/opai本地 為原始資料源。",
            "智能體優先讀取 500/llama32-chat/data/local_knowledge 下的整理資料。",
        ],
    }

    for name, path in SOURCE_MAP.items():
        manifest["sources"][name] = {
            "path": str(path),
            "link_path": str(HUB_DIR / name),
            **path_stats(path),
        }

    local_knowledge_db = (
        SOURCE_MAP["local_knowledge"] / "complete_chatgpt_database.json"
    )
    manifest["chatgpt_database_ready"] = local_knowledge_db.exists()
    manifest["chatgpt_database_path"] = str(local_knowledge_db)

    return manifest


def write_readme(manifest: dict) -> None:
    lines = [
        "# 知識中樞",
        "",
        "這裡是統一入口，不直接搬動原始資料。",
        "",
        "## 主要來源",
        "",
    ]

    for name, data in manifest["sources"].items():
        lines.append(
            f"- `{name}`: `{data['path']}` | files={data['files']} | exists={data['exists']}"
        )

    lines.extend(
        [
            "",
            "## ChatGPT 本地資料",
            "",
            f"- database_ready: {manifest['chatgpt_database_ready']}",
            f"- database_path: `{manifest['chatgpt_database_path']}`",
            "",
            "## 說明",
            "",
            "- `chatgpt_export/` 是原始資料",
            "- `local_knowledge/` 是整理後、供智能體檢索的資料層",
            "- `manifest.json` 給桌面端和記憶 API 讀取",
        ]
    )

    (HUB_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    HUB_DIR.mkdir(parents=True, exist_ok=True)

    for name, target in SOURCE_MAP.items():
        ensure_symlink(name, target)

    manifest = build_manifest()
    (HUB_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_readme(manifest)

    print("✅ 知識中樞已同步")
    print(f"   hub: {HUB_DIR}")
    for name, data in manifest["sources"].items():
        print(f"   - {name}: files={data['files']} exists={data['exists']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
