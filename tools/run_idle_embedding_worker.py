"""Run one idle embedding refresh pass against a Vault."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from core.autonomy import user_is_active
from core.data_paths import resolve_data_root
from core.embedding_client import NemotronEmbeddingClient
from core.idle_background_worker import EmbeddingRefreshJob, IdleBackgroundWorker, IdleWorkerConfig

ACTIVE_FOREGROUND_STATUSES = frozenset({"queued", "claimed", "running", "validating"})


def embedding_api_configured() -> bool:
    """Return whether the embedding client has a usable local credential."""
    return bool(
        str(os.getenv("NVIDIA_API_KEY", "") or "").strip()
        or str(os.getenv("NVAPI_API_KEY", "") or "").strip()
    )


def external_embedding_allowed() -> bool:
    """Require explicit consent before sending Vault text to a cloud API."""
    return str(os.getenv("WHITE_STUDIO_ALLOW_EXTERNAL_EMBEDDING", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def frontmatter_status(text: str) -> str:
    """Read only the top-level YAML status, not historical body text."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() == "status":
            return value.split("#", 1)[0].strip().strip("'\"").lower()
    return ""


def has_foreground_task(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return frontmatter_status(text) in ACTIVE_FOREGROUND_STATUSES


def should_stop_loop(status: str, loop: bool) -> bool:
    """Stop one-shot or terminal passes; retry only expected pauses/busy states."""
    return (not loop) or status in {"completed", "blocked"}


def next_sleep_seconds(result: dict[str, object], default_seconds: int) -> int:
    """Avoid polling during a persisted transient-provider backoff."""
    if result.get("status") != "deferred":
        return max(5, int(default_seconds))
    raw_until = str(result.get("defer_until") or "").strip()
    try:
        until = datetime.fromisoformat(raw_until.replace("Z", "+00:00"))
        remaining = int((until - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return max(5, int(default_seconds))
    return max(max(5, int(default_seconds)), remaining)


def write_heartbeat(path: Path, result: dict[str, object], *, loop: bool) -> dict[str, object]:
    """Publish non-secret worker liveness atomically for a watchdog."""
    payload = {
        "schema_version": 1,
        "worker": "idle-embedding-worker",
        "pid": os.getpid(),
        "loop": bool(loop),
        "status": str(result.get("status", "unknown")),
        "reason": str(result.get("reason", "")),
        "task_id": result.get("task_id"),
        "run_id": result.get("run_id"),
        "operation_id": result.get("operation_id"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return payload


def main() -> int:
    vault_root = Path(os.getenv("VAULT_WORKSPACE_ROOT", Path.cwd())).resolve()
    state_root = Path(
        os.getenv(
            "WHITE_STUDIO_EMBEDDING_STATE_DIR",
            vault_root / "runtime" / ".mcp-state" / "embedding-index",
        )
    ).resolve()
    shared_data_root = Path(
        os.getenv(
            "WHITE_STUDIO_AUTONOMY_ROOT",
            resolve_data_root(RUNTIME_ROOT),
        )
    ).resolve()
    client = NemotronEmbeddingClient()
    job = EmbeddingRefreshJob(vault_root, state_root, client=client)
    worker = IdleBackgroundWorker(
        vault_root,
        state_root,
        job=job,
        autonomy_root=shared_data_root / "autonomy",
    )
    loop = "--loop" in sys.argv
    interval = max(5, int(os.getenv("WHITE_STUDIO_IDLE_POLL_SECONDS", "30")))
    heartbeat_path = Path(
        os.getenv(
            "WHITE_STUDIO_IDLE_HEARTBEAT_PATH",
            state_root.parent / "idle-worker-heartbeat.json",
        )
    ).resolve()

    def foreground_pending() -> bool:
        paths = [vault_root / "智能體" / "chatgpt-inbox.md"]
        task_dir = vault_root / "智能體" / "tasks"
        if task_dir.is_dir():
            paths.extend(task_dir.glob("*.md"))
        return any(has_foreground_task(path) for path in paths)

    def signals() -> dict[str, object]:
        cpu = 0.0
        memory = 0.0
        try:
            import psutil

            cpu = float(psutil.cpu_percent(interval=0.1))
            memory = float(psutil.virtual_memory().percent)
        except Exception:
            pass
        activity_marker = shared_data_root / "activity" / "last_user_activity"
        activity_known = activity_marker.exists()
        return {
            # Missing activity evidence is fail-closed. Do not start a
            # background indexer merely because the marker was never created.
            "user_active": (not activity_known)
            or user_is_active(state_root.parent, window_seconds=300),
            "cpu_percent": cpu,
            "memory_percent": memory,
            "quota_sufficient": True,
            # Do not create a durable background task when the embedding
            # credential or explicit external-transfer consent is absent. The
            # API client remains the final guard, but the idle gate should
            # pause before claiming work.
            "external_embedding_allowed": external_embedding_allowed(),
            "services_healthy": embedding_api_configured() and external_embedding_allowed(),
        }

    while True:
        result = worker.run_once(
            signals=signals(),
            foreground_pending=foreground_pending(),
            foreground_probe=foreground_pending,
        )
        write_heartbeat(heartbeat_path, result, loop=loop)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if should_stop_loop(str(result.get("status", "blocked")), loop):
            return 0 if result.get("status") in {"completed", "paused"} else 5
        time.sleep(next_sleep_seconds(result, interval))


if __name__ == "__main__":
    raise SystemExit(main())
