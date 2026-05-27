#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install VS Code/Cursor extensions recommended by this workspace.

This keeps the Windows machine aligned with the Mac workspace without relying
on manually remembered extension names.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


LOCAL_EXTENSION_IDS = {
    "chengcheng-local.cursor-agent-sidebar",
}


def load_recommendations(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    recommendations = data.get("recommendations", [])
    if not isinstance(recommendations, list):
        raise ValueError(f"{path} recommendations must be a list")
    return [str(item).strip() for item in recommendations if str(item).strip()]


def install_extension(editor_cmd: str, extension_id: str, dry_run: bool) -> int:
    cmd = [editor_cmd, "--install-extension", extension_id]
    if dry_run:
        print("[dry-run]", " ".join(cmd))
        return 0
    print("[install]", extension_id)
    proc = subprocess.run(cmd, text=True, check=False)
    return int(proc.returncode or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install workspace VS Code/Cursor extensions")
    parser.add_argument("--editor", default="code", help="CLI command: code, cursor, or full path")
    parser.add_argument(
        "--extensions-file",
        default=".vscode/extensions.json",
        help="Path to VS Code recommendations JSON",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print install commands without running them")
    args = parser.parse_args()

    workspace = Path.cwd()
    extensions_file = (workspace / args.extensions_file).resolve()
    if not extensions_file.exists():
        print(f"[error] missing {extensions_file}", file=sys.stderr)
        return 1

    editor_path = shutil.which(args.editor) or args.editor
    if not args.dry_run and shutil.which(args.editor) is None and not Path(args.editor).exists():
        print(
            f"[error] cannot find editor command '{args.editor}'. "
            "Install VS Code/Cursor CLI first, or pass --editor with the full executable path.",
            file=sys.stderr,
        )
        return 1

    failures: list[str] = []
    for extension_id in load_recommendations(extensions_file):
        if extension_id in LOCAL_EXTENSION_IDS:
            print(f"[skip-local] {extension_id} -> install with cursor-agent-sidebar-extension VSIX")
            continue
        rc = install_extension(editor_path, extension_id, args.dry_run)
        if rc != 0:
            failures.append(extension_id)

    if failures:
        print("[failed]", ", ".join(failures), file=sys.stderr)
        return 1

    print("[ok] extension recommendations processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
