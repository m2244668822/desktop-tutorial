from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError("migration_manifest_missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("migration_manifest_invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("migration_manifest_invalid")
    return payload


def _integer(payload: Mapping[str, Any], key: str) -> int:
    try:
        return max(0, int(payload.get(key, 0) or 0))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("migration_manifest_invalid") from exc


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_public_migration_status(
    source_directory: str | Path,
    destination_directory: str | Path,
) -> dict[str, dict[str, Any]]:
    source = Path(source_directory)
    destination = Path(destination_directory)
    device_source = _read_manifest(source / "trevor_data_manifest.json")
    graphiti_source = _read_manifest(source / "graphiti_manifest.json")

    failed_count = _integer(graphiti_source, "failed_count")
    migrated_count = _integer(graphiti_source, "migrated_count")
    source_count = _integer(graphiti_source, "source_count")
    if (
        graphiti_source.get("completed") is not True
        or failed_count != 0
        or migrated_count < source_count
    ):
        raise RuntimeError("graphiti_migration_incomplete")

    batching_source = graphiti_source.get("batching")
    batching = {}
    if isinstance(batching_source, Mapping):
        for key in ("strategy", "max_turns", "max_utf8_bytes", "batch_count"):
            if key in batching_source:
                batching[key] = batching_source[key]

    device = {
        "schema_version": int(device_source.get("schema_version", 1) or 1),
        "identity": "trevor",
        "generated_at": str(device_source.get("generated_at", "") or ""),
        "unique_turns": _integer(device_source, "unique_turns"),
        "conversation_threads": _integer(device_source, "conversation_threads"),
        "deduplication": str(
            device_source.get("deduplication", "sha256_normalized_turn")
            or "sha256_normalized_turn"
        ),
        "rerunnable": bool(device_source.get("rerunnable", True)),
        "encrypted": True,
        "public_status_only": True,
    }
    graphiti = {
        "schema_version": int(graphiti_source.get("schema_version", 1) or 1),
        "graphiti_version": str(graphiti_source.get("graphiti_version", "") or ""),
        "identity": "trevor",
        "generated_at": str(graphiti_source.get("generated_at", "") or ""),
        "migrated_count": migrated_count,
        "source_count": source_count,
        "failed_count": failed_count,
        "completed": True,
        "status": "completed",
        "deduplication": str(
            graphiti_source.get("deduplication", "sha256_normalized_turn")
            or "sha256_normalized_turn"
        ),
        "redacted_before_upload": True,
        "rerunnable": bool(graphiti_source.get("rerunnable", True)),
        "batching": batching,
        "public_status_only": True,
    }
    _atomic_json(destination / "trevor_data_manifest.json", device)
    _atomic_json(destination / "graphiti_manifest.json", graphiti)
    return {"device": device, "graphiti": graphiti}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export privacy-safe Trevor migration status manifests"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    result = export_public_migration_status(args.source, args.destination)
    print(
        json.dumps(
            {
                "ok": True,
                "destination": str(args.destination.expanduser().resolve()),
                "unique_turns": result["device"]["unique_turns"],
                "conversation_threads": result["device"]["conversation_threads"],
                "migrated_count": result["graphiti"]["migrated_count"],
                "source_count": result["graphiti"]["source_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["export_public_migration_status"]
