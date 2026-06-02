#!/usr/bin/env python3
"""Generate a portable Perob architecture and progress report."""

from __future__ import annotations

import json
import socket
import subprocess
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "dev" / "SYSTEM_FRAMEWORK_RELATIONSHIP_AND_PROGRESS_MASTER_2026-06-02.md"
DESKTOP_COPY = Path.home() / "Desktop" / "城城城程式"
RESCUED_FILES = [
    ".githooks/commit-msg",
    ".githooks/pre-push",
    "docs/dev/AGENT_GIT_AUTOPILOT.md",
    "docs/dev/BRANCH_PROTECTION_POLICY.md",
    "tools/agent_git_autopilot.py",
]
SKIP_PARTS = {
    ".git",
    ".claude",
    ".cursor",
    ".gemini",
    ".playwright-cli",
    ".pytest_cache",
    ".python-installations",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    ".venv312",
    ".venv-faiss",
    "node_modules",
    "__pycache__",
    "data",
    "data_hdd_storage",
    "logs",
}


def run(*args: str) -> str:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    return completed.stdout.strip()


def tcp_up(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def get_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {}


def disk_markdown_files(*, include_runtime: bool = False) -> list[str]:
    rows = []
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT)
        skip_parts = (
            SKIP_PARTS
            if not include_runtime
            else {".git", "node_modules", "__pycache__"}
        )
        if any(
            part in skip_parts
            or part.startswith(".venv")
            or part.startswith(".git_corrupt_backup")
            for part in rel.parts
        ):
            continue
        if rel.parts[:2] in {
            ("archive", "backups"),
            ("archive", "case_collision_backups"),
        }:
            continue
        rows.append(rel.as_posix())
    return sorted(rows)


def markdown_layer(path: str) -> str:
    if path.startswith("docs/dev/"):
        return "docs/dev：現行治理主幹"
    if path.startswith("docs/runbooks/"):
        return "docs/runbooks：可操作 SOP"
    if path.startswith("reports/"):
        return "reports：狀態快照與證據"
    if path.startswith("archive/"):
        return "archive：歷史資料"
    if path.startswith("500/llama32-chat/docs/"):
        return "500/llama32-chat/docs：legacy 對照"
    return "其他：待逐步整理"


def bullet_rows(rows: list[str], empty: str = "無") -> str:
    return "\n".join(f"- `{row}`" for row in rows) if rows else f"- {empty}"


def main() -> None:
    tracked_md = sorted(
        filter(
            None,
            run("git", "-c", "core.quotepath=false", "ls-files", "*.md").splitlines(),
        )
    )
    disk_md = disk_markdown_files()
    all_disk_md = disk_markdown_files(include_runtime=True)
    tracked_set = set(tracked_md)
    disk_set = set(disk_md)
    all_disk_set = set(all_disk_md)
    missing_on_disk = sorted(tracked_set - all_disk_set)
    excluded_runtime_tracked = sorted((tracked_set & all_disk_set) - disk_set)
    untracked_on_disk = sorted(disk_set - tracked_set)
    layers: dict[str, list[str]] = defaultdict(list)
    for path in disk_md:
        layers[markdown_layer(path)].append(path)

    branch = run("git", "branch", "--show-current") or "unknown"
    remote_head = run("git", "rev-parse", "--short", "origin/codex/training-overlay-20260525") or "unknown"
    local_head = run("git", "rev-parse", "--short", "HEAD") or "unknown"
    worktree = run("git", "status", "--short") or "clean"
    live = get_json("http://127.0.0.1:5001/health/live")
    ready = get_json("http://127.0.0.1:5001/health/ready")
    topology = get_json("http://127.0.0.1:5001/api/runtime/topology")
    knowledge_hub = ready.get("knowledge_hub", {})
    topology_services = topology.get("services", {})
    openclaw_service = topology_services.get("openclaw", {})
    rescued = [path for path in RESCUED_FILES if (ROOT / path).exists()]

    layer_sections = []
    for layer, files in sorted(layers.items()):
        layer_sections.append(f"### {layer}\n\n共 `{len(files)}` 筆。\n\n{bullet_rows(files[:80])}")
    layer_text = "\n\n".join(layer_sections)

    report = f"""# Perob 系統框架、關係圖與進度主控報告

產生時間：{datetime.now().isoformat(timespec="seconds")}

## 1. 系統摘要與已驗證真相

| 項目 | 實測結果 | 判定 |
|---|---|---|
| 正式工作區 | `{ROOT}` | 外接硬碟為唯一正式執行工作區 |
| Git 分支 | `{branch}` | 整合分支 |
| 本地 HEAD | `{local_head}` | 可追查 |
| 遠端基線 HEAD | `{remote_head}` | 已保留遠端真相來源 |
| Web `5001` | `{"up" if tcp_up(5001) else "down"}` | 前端與 API 單一入口 |
| TLS `5443` | `{"up" if tcp_up(5443) else "down"}` | HTTPS 大門 |
| OpenClaw `18789` | `{"up" if tcp_up(18789) else "down"}` | 分階段控制平面 |
| Ollama `11434` | `{"up" if tcp_up(11434) else "down"}` | 本地模型回退 |
| n8n `5678` | `{"up" if tcp_up(5678) else "down"}` | 可選，不列入核心啟動 |
| readiness | `{ready.get("status", "unavailable")}` | 必要條件：`{ready.get("required_ready", False)}` |
| FAISS | `{knowledge_hub.get("faiss_ready", False)}` | 背景重建，不堵塞 Web request |
| SQLite | `{knowledge_hub.get("sqlite_ready", False)}` | 記憶層可用 |

生活化理解：瀏覽器是大門，`5443` 是門禁與 TLS，`5001` 是同時負責櫃台與廚房的 Perob 主服務，`18789` 是新增的 OpenClaw 調度室。調度室故障時，廚房仍可走原生 DesktopBridge 回退路徑，不會整間餐廳停擺。

## 2. Git、工作樹與 Desktop 救援

### Git 工作樹

```text
{worktree}
```

### Desktop 舊副本

| 項目 | 狀態 |
|---|---|
| `/Users/user/Desktop/城城城程式` | `{"仍存在，等待推送與 checksum 驗證後刪除" if DESKTOP_COPY.exists() else "已清理"}` |
| 已救援檔案 | `{len(rescued)}/{len(RESCUED_FILES)}` |

{bullet_rows(rescued)}

## 3. 系統關係圖

```mermaid
flowchart LR
  Browser["瀏覽器 / Windows LAN 用戶"] --> TLS["HTTPS Proxy :5443"]
  TLS --> Perob["Perob UI + API :5001"]
  Perob --> Bridge["DesktopBridge 緊急回退"]
  Perob --> OpenClaw["OpenClaw Gateway :18789"]
  OpenClaw --> Lobster["Lobster deterministic workflows"]
  Perob --> Ollama["Ollama :11434"]
  Perob --> SQLite["SQLite 記憶層"]
  Perob --> FAISS["FAISS 向量索引"]
  Perob --> Git["Git 遠端治理"]
  Perob -. optional .-> N8N["n8n :5678"]
  Lobster --> Agents["申言者 / 工程師 / 帽子 / 小編 / 研究中樞 / 通用"]
```

## 4. Mac、Windows 與 LAN 相容性矩陣

| 環境 | 入口 | 狀態 | 備註 |
|---|---|---|---|
| Mac 本機 | `https://perob.com:5443/Perob` | 可用 | `/etc/hosts` 最終只保留 `127.0.0.1 perob.com` |
| Mac 除錯 | `http://127.0.0.1:5001/chat_shell` | 可用 | 跳過 TLS，適合快速確認 |
| Windows LAN | `https://<Mac-LAN-IP>:5443/Perob` | 待驗證 | 不與 Mac 本機 `perob.com` hosts 混用 |
| OpenClaw Gateway | `ws://<Mac-LAN-IP>:18789` | 需 token | LAN 模式，token 不提交 Git |
| 外接硬碟啟動 | `bash tools/manage_perob_stack.sh restart` | 可用 | 預設 Terminal-safe；LaunchAgent 需 Python 完整磁碟存取 |

## 5. Markdown 文件分層索引

| 統計 | 數量 |
|---|---:|
| Git 追蹤 MD | {len(tracked_md)} |
| 可治理磁碟 MD | {len(disk_md)} |
| Git 已追蹤但磁碟缺失 | {len(missing_on_disk)} |
| 已追蹤但刻意排除的 runtime MD | {len(excluded_runtime_tracked)} |
| 磁碟存在但未追蹤 | {len(untracked_on_disk)} |

{layer_text}

### Git 已追蹤但磁碟缺失

{bullet_rows(missing_on_disk)}

### 已追蹤但刻意排除的 runtime MD

{bullet_rows(excluded_runtime_tracked)}

### 磁碟存在但未追蹤

{bullet_rows(untracked_on_disk[:120])}

## 6. 統一進度表

| 模組 | 目前狀態 | 完成條件 |
|---|---|---|
| Git 對齊 | 整合分支 `{branch}` 已建立 | 完整驗證後推送遠端 |
| Desktop 舊版 | 已救援 `{len(rescued)}` 筆附件 | checksum 驗證、推送後刪除 |
| Web `5001` | `{live.get("status", "unavailable")}` | live 與 ready 均通過 |
| TLS `5443` | `{"ready" if tcp_up(5443) else "down"}` | `/Perob` HEAD/GET 均導向 `/chat_shell` |
| OpenClaw `18789` | `{openclaw_service.get("status", "unavailable")}` | Gateway token、RPC 與 Lobster allowlist 通過 |
| Lobster | allowlist 已要求啟用 | 加入高風險 approval workflow 實測 |
| FAISS | `{knowledge_hub.get("faiss_ready", False)}` | manifest 使用可攜路徑 |
| Workflow rerun | HTTP 路由已補齊 | 前端帶有效 task id 重跑通過 |
| 診斷工具 | 已移除 legacy 誤報 | 持續監控趨勢與 swap |
| hosts | 仍需人工授權正規化 | 只保留本機 `127.0.0.1 perob.com` |

## 7. 風險排名與下一階段 backlog

| 優先級 | 風險 | 下一步 |
|---|---|---|
| P1 | `/etc/hosts` 同時存在 LAN IP 與 localhost | 執行 `bash tools/normalize_perob_hosts.sh`，依提示使用一次 sudo |
| P1 | 外接卷宗下 LaunchAgent 受 macOS TCC 限制 | 保留 Terminal-safe 模式；若要 daemon 化，授予 Python 完整磁碟存取後再開 `PEROB_USE_LAUNCHAGENT=1` |
| P2 | OpenClaw 任務轉送尚未設定 endpoint | 先維持 adapter 健康狀態與 DesktopBridge 回退，再做 approval workflow |
| P2 | n8n 未啟動 | 保持可選，不混入核心登入鏈 |
| P2 | 歷史工作流含失敗紀錄 | 以有效 task id 實測 rerun，逐步清理 |
| P3 | Markdown 文件仍有歷史散件 | 持續以本 generator 分類，不直接批次刪除 |

## 8. 可重跑驗證指令

```bash
cd "{ROOT}"
python3 tools/generate_system_framework_master_report.py
python3 -m py_compile core/web_server.py core/openclaw_adapter.py core/knowledge_hub.py desktop_chat_app.py chatgpt_server.py SYSTEM_DIAGNOSTIC.py
python3 -m unittest tests.test_perob_mainline_health_contract -v
curl -sS http://127.0.0.1:5001/health/live
curl -sS http://127.0.0.1:5001/health/ready
curl -k --resolve perob.com:5443:127.0.0.1 https://perob.com:5443/status
openclaw gateway status --json
```
"""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    print(f"generated: {REPORT}")
    print(f"tracked_md={len(tracked_md)} disk_md={len(disk_md)}")


if __name__ == "__main__":
    main()
