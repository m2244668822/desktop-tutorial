#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synchronize the Knowledge Hub manifest for Windows/macOS shared workspaces.

This script only writes lightweight index files under data/knowledge_hub. It does
not delete or move source data.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.data_paths import ProjectPaths, is_link_like
from core.knowledge_hub import KnowledgeHub


def _path_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "files": 0, "size_bytes": 0, "latest_mtime": ""}

    if path.is_file():
        return {
            "exists": True,
            "files": 1,
            "size_bytes": path.stat().st_size,
            "latest_mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        }

    files = [p for p in path.rglob("*") if p.is_file()]
    latest_mtime = max((p.stat().st_mtime for p in files), default=0)
    return {
        "exists": True,
        "files": len(files),
        "size_bytes": sum(p.stat().st_size for p in files),
        "latest_mtime": datetime.fromtimestamp(latest_mtime).isoformat()
        if latest_mtime
        else "",
    }


def _source_map(paths: ProjectPaths) -> dict[str, Path]:
    return {
        "docs": paths.root / "docs",
        "reports": paths.root / "reports",
        "logs": paths.root / "logs",
        "local_knowledge": paths.llama_data / "local_knowledge",
        "agent_memories": paths.data / "agent_memories",
        "memory_layers": paths.data / "knowledge_hub" / "memory_layers",
    }


def build_manifest(workspace: str | Path = BASE_DIR) -> dict[str, Any]:
    paths = ProjectPaths(workspace)
    hub = KnowledgeHub(paths.root)
    status = hub.status()
    data_entry = paths.root / "data"

    manifest: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "workspace": str(paths.root),
        "data_root": str(paths.data),
        "data_entry_is_link_like": is_link_like(data_entry),
        "hub_dir": str(paths.data / "knowledge_hub"),
        "chatgpt_database_ready": bool(status.get("chatgpt_database_ready")),
        "chatgpt_database_path": status.get("chatgpt_database_path", ""),
        "chatgpt_local_index_path": status.get("chatgpt_local_index_path", ""),
        "sqlite_ready": bool(status.get("sqlite_ready")),
        "faiss_ready": bool(status.get("faiss_ready")),
        "total_items": int(status.get("total_items", 0) or 0),
        "by_source": status.get("by_source", {}),
        "sqlite_path": status.get("sqlite_path", ""),
        "faiss_path": status.get("faiss_path", ""),
        "meta_path": status.get("meta_path", ""),
        "sources": {},
        "notes": [
            "Windows/macOS 共用工作區以 data/knowledge_hub/manifest.json 作為狀態交接卡。",
            "ChatGPT DB 是原始大資料庫；SQLite 是整理後的書架；FAISS 是快速查找索引。",
            "本腳本只更新 manifest 與 README，不刪除、不搬移資料。",
        ],
    }

    for name, path in _source_map(paths).items():
        manifest["sources"][name] = {
            "path": str(path),
            **_path_stats(path),
        }

    return manifest


def write_readme(manifest: dict[str, Any], hub_dir: Path) -> None:
    ready = "就緒" if manifest.get("faiss_ready") else "需檢查"
    lines = [
        "# Knowledge Hub 交接卡",
        "",
        f"- 產生時間：{manifest.get('generated_at', '')}",
        f"- 工作區：`{manifest.get('workspace', '')}`",
        f"- 資料入口：`{manifest.get('data_root', '')}`",
        f"- ChatGPT 長期記憶庫：{'就緒' if manifest.get('chatgpt_database_ready') else '未就緒'}",
        f"- SQLite：{'就緒' if manifest.get('sqlite_ready') else '未就緒'}",
        f"- FAISS：{'就緒' if manifest.get('faiss_ready') else '未就緒'}",
        f"- 索引筆數：{manifest.get('total_items', 0)}",
        f"- 整體判斷：{ready}",
        "",
        "## 生活化理解",
        "",
        "- ChatGPT DB 像整箱原始筆記。",
        "- SQLite 像已經分類放上書架的卡片盒。",
        "- FAISS 像書架旁邊的超快索引員，能用語意找相近內容。",
        "- manifest 像貼在門口的交接便條，Windows 和 Mac 都先看它確認資料在哪裡。",
        "",
        "## 來源清單",
        "",
    ]
    for name, data in manifest.get("sources", {}).items():
        lines.append(
            f"- `{name}`：exists={data.get('exists')} files={data.get('files')} path=`{data.get('path')}`"
        )
    lines.extend(
        [
            "",
            "## 注意",
            "",
            "- 若 manifest 缺失但 SQLite/FAISS 檔案存在，代表資料本體還在，只是交接卡要重建。",
            "- 若 Mac 端路徑不同，請先跑本腳本重新生成 manifest，不要直接沿用 Windows 絕對路徑。",
        ]
    )
    (hub_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    paths = ProjectPaths(BASE_DIR)
    hub_dir = paths.data / "knowledge_hub"
    hub_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(paths.root)
    manifest_path = hub_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_readme(manifest, hub_dir)

    print("Knowledge Hub manifest synced")
    print(f"manifest: {manifest_path}")
    print(f"ChatGPT DB: {'ready' if manifest['chatgpt_database_ready'] else 'missing'}")
    print(f"SQLite: {'ready' if manifest['sqlite_ready'] else 'missing'}")
    print(f"FAISS: {'ready' if manifest['faiss_ready'] else 'missing'}")
    print(f"total_items: {manifest['total_items']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
