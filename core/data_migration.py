from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.audit_chain import HashChainAuditLog
from core.encrypted_store import AESGCMJsonStore, DeviceEncryptionKey
from core.trevor_identity import TREVOR_DISPLAY_NAME, normalize_trevor_identity


def _turn_hash(user: Any, assistant: Any) -> str:
    normalized = "\n".join(
        " ".join(str(value or "").split()).strip().lower()
        for value in (user, assistant)
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class TrevorDataMigrator:
    def __init__(
        self,
        workspace: str | Path,
        destination: str | Path,
        *,
        json_store: AESGCMJsonStore | None = None,
        audit_log: HashChainAuditLog | None = None,
    ):
        self.workspace = Path(workspace).expanduser().resolve()
        self.destination = Path(destination).expanduser().resolve()
        self.destination.mkdir(parents=True, exist_ok=True)
        self.json_store = json_store or AESGCMJsonStore(DeviceEncryptionKey().get_or_create)
        self.audit_log = audit_log or HashChainAuditLog(
            self.destination / "audit" / "events.jsonl"
        )
        self._turns: set[str] = set()
        self._conversations: dict[str, dict[str, Any]] = {}
        self._source_counts: dict[str, int] = {}

    def _copy_runtime_files(self) -> int:
        copied = 0
        for source_root in (
            self.workspace / "data",
            self.workspace / "data_hdd_storage",
        ):
            if not source_root.is_dir():
                continue
            for source in source_root.rglob("*"):
                if not source.is_file() or ".tmp-" in source.name:
                    continue
                relative = source.relative_to(source_root)
                if relative == Path("agent_memories/conversations.json"):
                    continue
                try:
                    envelope = json.loads(source.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(envelope, dict) or envelope.get("algorithm") != "AES-256-GCM":
                    continue
                target = self.destination / relative
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied += 1
        return copied

    def _read_private_json(self, path: Path, default: Any) -> Any:
        try:
            return self.json_store.read_json(path, default)
        except Exception:
            raise RuntimeError("private_migration_source_unreadable")

    def _add_turn(
        self,
        *,
        source: str,
        thread_hint: str,
        source_role: str,
        timestamp: str,
        user: Any,
        assistant: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        user_text = str(user or "").strip()
        assistant_text = str(assistant or "").strip()
        if not user_text and not assistant_text:
            return
        content_hash = _turn_hash(user_text, assistant_text)
        if content_hash in self._turns:
            return
        self._turns.add(content_hash)
        identity = normalize_trevor_identity(role=source_role)
        thread_id = hashlib.sha256(
            f"{source}:{thread_hint}".encode("utf-8")
        ).hexdigest()[:24]
        thread = self._conversations.setdefault(
            thread_id,
            {
                "agent_name": TREVOR_DISPLAY_NAME,
                "created_at": timestamp,
                "last_message_at": timestamp,
                "messages": [],
            },
        )
        safe_metadata = dict(metadata or {})
        safe_metadata.update(
            {
                "source": source,
                "source_role": source_role,
                "capability_mode": identity.capability_mode,
                "content_hash": content_hash,
            }
        )
        thread["messages"].append(
            {
                "timestamp": timestamp,
                "user": user_text,
                "assistant": assistant_text,
                "metadata": safe_metadata,
            }
        )
        if timestamp and timestamp > str(thread.get("last_message_at", "")):
            thread["last_message_at"] = timestamp
        self._source_counts[source] = self._source_counts.get(source, 0) + 1

    def _ingest_manager_file(self, path: Path, source: str) -> None:
        payload = self._read_private_json(path, {})
        if not isinstance(payload, dict):
            return
        for thread_id, thread in payload.items():
            if not isinstance(thread, dict):
                continue
            source_role = str(thread.get("agent_name", TREVOR_DISPLAY_NAME) or TREVOR_DISPLAY_NAME)
            for index, message in enumerate(thread.get("messages", []) or []):
                if not isinstance(message, dict):
                    continue
                self._add_turn(
                    source=source,
                    thread_hint=f"{thread_id}:{index}",
                    source_role=str(
                        (message.get("metadata") or {}).get("source_role", source_role)
                    ),
                    timestamp=str(message.get("timestamp", thread.get("created_at", "")) or ""),
                    user=message.get("user", ""),
                    assistant=message.get("assistant", ""),
                    metadata=message.get("metadata", {}),
                )

    def _ingest_legacy_list(self, path: Path) -> None:
        payload = self._read_private_json(path, [])
        if not isinstance(payload, list):
            return
        for index, row in enumerate(payload):
            if not isinstance(row, dict):
                continue
            self._add_turn(
                source="legacy_llama32_chat",
                thread_hint=str(index),
                source_role="通用",
                timestamp=str(row.get("timestamp", "") or ""),
                user=row.get("prompt", ""),
                assistant=row.get("response", ""),
                metadata={
                    "model": row.get("model", ""),
                    "status": row.get("status", ""),
                },
            )

    def migrate(self) -> dict[str, Any]:
        self._turns.clear()
        self._conversations.clear()
        self._source_counts.clear()
        copied_files = self._copy_runtime_files()
        destination_file = self.destination / "agent_memories" / "conversations.json"
        self._ingest_manager_file(destination_file, "trevor_runtime")
        self._ingest_manager_file(
            self.workspace / "data" / "agent_memories" / "conversations.json",
            "workspace_data",
        )
        self._ingest_manager_file(
            self.workspace / "data_hdd_storage" / "agent_memories" / "conversations.json",
            "workspace_hdd",
        )
        self._ingest_legacy_list(
            self.workspace / "500" / "llama32-chat" / "data" / "conversations.json"
        )
        self.json_store.write_json(destination_file, self._conversations)
        manifest = {
            "schema_version": 1,
            "identity": "trevor",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "unique_turns": len(self._turns),
            "conversation_threads": len(self._conversations),
            "copied_files": copied_files,
            "source_counts": dict(sorted(self._source_counts.items())),
            "deduplication": "sha256_normalized_turn",
            "rerunnable": True,
        }
        _atomic_json(
            self.destination / "migrations" / "trevor_data_manifest.json",
            manifest,
        )
        self.audit_log.append(
            "data_migration_completed",
            {
                "target": "trevor_device_store",
                "unique_turns": manifest["unique_turns"],
                "conversation_threads": manifest["conversation_threads"],
                "copied_encrypted_files": manifest["copied_files"],
                "rerunnable": True,
                "encrypted": True,
            },
        )
        return manifest


__all__ = ["TrevorDataMigrator"]
