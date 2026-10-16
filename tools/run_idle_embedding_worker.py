"""Run one idle embedding refresh pass against a Vault."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from core.autonomy import user_is_active
from core.embedding_client import NemotronEmbeddingClient
from core.idle_background_worker import EmbeddingRefreshJob, IdleBackgroundWorker, IdleWorkerConfig


def main() -> int:
    vault_root = Path(os.getenv("VAULT_WORKSPACE_ROOT", Path.cwd())).resolve()
    state_root = Path(
        os.getenv(
            "WHITE_STUDIO_EMBEDDING_STATE_DIR",
            vault_root / "runtime" / ".mcp-state" / "embedding-index",
        )
    ).resolve()
    client = NemotronEmbeddingClient()
    job = EmbeddingRefreshJob(vault_root, state_root, client=client)
    worker = IdleBackgroundWorker(vault_root, state_root, job=job)
    loop = "--loop" in sys.argv
    interval = max(5, int(os.getenv("WHITE_STUDIO_IDLE_POLL_SECONDS", "30")))

    def foreground_pending() -> bool:
        paths = [vault_root / "智能體" / "chatgpt-inbox.md"]
        task_dir = vault_root / "智能體" / "tasks"
        if task_dir.is_dir():
            paths.extend(task_dir.glob("*.md"))
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "status: queued" in text or "status: running" in text:
                return True
        return False

    def signals() -> dict[str, object]:
        cpu = 0.0
        memory = 0.0
        try:
            import psutil

            cpu = float(psutil.cpu_percent(interval=0.1))
            memory = float(psutil.virtual_memory().percent)
        except Exception:
            pass
        activity_marker = state_root.parent / "activity" / "last_user_activity"
        activity_known = activity_marker.exists()
        return {
            # Missing activity evidence is fail-closed. Do not start a
            # background indexer merely because the marker was never created.
            "user_active": (not activity_known)
            or user_is_active(state_root.parent, window_seconds=300),
            "cpu_percent": cpu,
            "memory_percent": memory,
            "quota_sufficient": True,
            "services_healthy": True,
        }

    while True:
        result = worker.run_once(
            signals=signals(),
            foreground_pending=foreground_pending(),
            foreground_probe=foreground_pending,
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if not loop or result.get("status") == "completed":
            return 0 if result.get("status") in {"completed", "paused"} else 5
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
