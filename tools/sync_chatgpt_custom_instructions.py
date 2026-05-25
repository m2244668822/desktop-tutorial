#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync the latest ChatGPT custom instructions into the desktop agent system."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "config" / "agent_profiles"
SYNCED_PROMPT_MD = PROFILE_DIR / "synced_chatgpt_custom_instructions.md"
SYNCED_PROMPT_JSON = PROFILE_DIR / "synced_chatgpt_custom_instructions.json"
DEFAULT_SOURCE_CANDIDATES = (
    "500/llama32-chat/openai_format_analysis.json",
    "500/llama32-chat/data/local_knowledge/complete_chatgpt_database.json",
)


def decode_json_string_value(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw.replace("\\n", "\n").replace("\\t", "\t").strip()


def extract_custom_instructions(path: Path) -> dict[str, str] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    model_matches = [
        decode_json_string_value(match).strip()
        for match in re.findall(
            r'"about_model_message"\s*:\s*"((?:\\.|[^"\\])*)"', text
        )
    ]
    user_matches = [
        decode_json_string_value(match).strip()
        for match in re.findall(r'"about_user_message"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    ]

    about_model = next((item for item in reversed(model_matches) if item), "")
    about_user = next((item for item in reversed(user_matches) if item), "")

    if not about_model and not about_user:
        return None
    if about_user.startswith("Other Information:"):
        about_user = about_user.replace("Other Information:", "", 1).strip()

    return {
        "source_path": str(path.resolve()),
        "about_model_message": about_model,
        "about_user_message": about_user,
    }


def choose_source(workspace: Path, explicit_source: str | None) -> dict[str, str]:
    candidates: list[Path] = []
    if explicit_source:
        candidates.append(Path(explicit_source).expanduser().resolve())
    else:
        for rel_path in DEFAULT_SOURCE_CANDIDATES:
            candidates.append((workspace / rel_path).resolve())
            if workspace != BASE_DIR:
                candidates.append((BASE_DIR / rel_path).resolve())

    seen = set()
    ranked: list[tuple[float, dict[str, str]]] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        extracted = extract_custom_instructions(candidate)
        if not extracted:
            continue
        mtime = candidate.stat().st_mtime
        ranked.append((mtime, extracted))

    if not ranked:
        searched = [str(path) for path in candidates]
        raise FileNotFoundError(
            "找不到可用的 ChatGPT custom instructions 來源。已搜尋：\n- "
            + "\n- ".join(searched)
        )

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def render_markdown(payload: dict[str, str]) -> str:
    lines = [
        "# Synced ChatGPT Custom Instructions",
        "",
        "這份檔案由 `tools/sync_chatgpt_custom_instructions.py` 自動產生。",
        "桌面智能體會優先讀取這份同步檔，而不是掃描大型匯出資料。",
        "",
        f"- synced_at: {datetime.now().isoformat()}",
        f"- source_path: `{payload['source_path']}`",
        "",
        "## 關於使用者",
        "",
        payload.get("about_user_message", "").strip() or "（未提供）",
        "",
        "## 希望助理如何回應",
        "",
        payload.get("about_model_message", "").strip() or "（未提供）",
        "",
        "## 套用規則",
        "",
        "- 這是全智能體共用層。",
        "- 不覆蓋各角色自己的專業定位。",
        "- 若角色 prompt 與此檔衝突，以安全限制與角色職責優先。",
        "",
    ]
    return "\n".join(lines)


def write_outputs(payload: dict[str, str]) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "synced_at": datetime.now().isoformat(),
        "source_path": payload["source_path"],
        "about_user_message": payload.get("about_user_message", ""),
        "about_model_message": payload.get("about_model_message", ""),
    }
    SYNCED_PROMPT_JSON.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    SYNCED_PROMPT_MD.write_text(render_markdown(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync ChatGPT custom instructions into the agent system."
    )
    parser.add_argument("--workspace", type=str, default=".", help="Workspace root.")
    parser.add_argument(
        "--source", type=str, default="", help="Explicit export file path."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only, do not write files."
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    payload = choose_source(workspace, args.source or None)

    print("== ChatGPT Custom Instructions Sync ==")
    print(f"workspace: {workspace}")
    print(f"source: {payload['source_path']}")
    print(f"about_user_message: {'yes' if payload.get('about_user_message') else 'no'}")
    print(
        f"about_model_message: {'yes' if payload.get('about_model_message') else 'no'}"
    )

    if args.dry_run:
        print("\n[Preview]")
        print(render_markdown(payload))
        return 0

    write_outputs(payload)
    print(f"\nSynced markdown -> {SYNCED_PROMPT_MD}")
    print(f"Synced metadata -> {SYNCED_PROMPT_JSON}")
    print("桌面智能體下次建立 prompt 時，會優先讀這份同步檔。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
