#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit this workspace for Mac/Windows portability.

The report focuses on things that usually break when the same project is moved
between macOS external volumes and a Windows machine: symlinks, case collisions,
missing runtime files, hard-coded volume paths, and required agent/skill data.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    "system_main.py",
    "desktop_chat_app.py",
    "start_desktop_chat_app.sh",
    "requirements.txt",
    "templates/chat.html",
    "templates/chat_shell.html",
    "templates/monitor_shell.html",
    "templates/agent_shell.html",
    "tools/check_desktop_runtime.py",
    "tools/check_case_collisions.py",
]

REQUIRED_DIRS = [
    "config",
    "data_hdd_storage",
    "data_hdd_storage/agent_memories",
    "data_hdd_storage/knowledge_hub",
    "skills",
    ".gemini/skills",
    "tools",
    "core",
]

SKILL_FILES = [
    "skills/brain-spirit-guide/SKILL.md",
    "skills/memory-retriever/SKILL.md",
    "skills/traffic-optimizer/SKILL.md",
    "skills/workspace-butler/SKILL.md",
    ".gemini/skills/brain-spirit-guide/SKILL.md",
    ".gemini/skills/memory-retriever/SKILL.md",
    ".gemini/skills/traffic-optimizer/SKILL.md",
    ".gemini/skills/workspace-butler/SKILL.md",
]

HARD_CODE_PATTERNS = [
    "/Volumes/",
    "/Users/",
    "C:\\Users\\",
]

SCAN_EXTENSIONS = {
    ".py",
    ".sh",
    ".md",
    ".json",
    ".html",
    ".js",
    ".css",
    ".ps1",
}

IGNORE_DIR_NAMES = {
    ".git",
    ".venv",
    ".venv-win",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    "node_modules",
    "dist",
    "build",
    "logs",
    "archive",
    "PID?豢?",
}


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return int(proc.returncode or 0), proc.stdout.strip()


def resolve_health_command(base: Path) -> list[str]:
    shell_entry = base / "start_desktop_chat_app.sh"
    if os.name != "nt" and shell_entry.exists():
        return [str(shell_entry), "health"]

    if os.name == "nt":
        python_candidates = [base / ".venv" / "Scripts" / "python.exe"]
    else:
        python_candidates = [base / ".venv" / "bin" / "python"]

    python_bin = next((p for p in python_candidates if p.exists()), Path(sys.executable))
    return [str(python_bin), str(base / "system_main.py"), "health"]


def case_collision_scan(base: Path) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [name for name in dirs if name not in IGNORE_DIR_NAMES]
        grouped: dict[str, list[str]] = {}
        for name in dirs + files:
            grouped.setdefault(name.casefold(), []).append(name)
        clashes = [sorted(names) for names in grouped.values() if len(names) > 1]
        if clashes:
            buckets.append({"path": str(Path(root)), "collisions": clashes})
    return buckets


def scan_hardcoded_paths(base: Path) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [name for name in dirs if name not in IGNORE_DIR_NAMES]
        root_path = Path(root)
        for name in files:
            path = root_path / name
            if path.suffix not in SCAN_EXTENSIONS:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            found = [pattern for pattern in HARD_CODE_PATTERNS if pattern in text]
            if found:
                hits.append(
                    {
                        "path": str(path.relative_to(base)),
                        "patterns": found,
                    }
                )
    return hits


def symlink_report(base: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [name for name in dirs if name not in IGNORE_DIR_NAMES]
        root_path = Path(root)
        for name in dirs + files:
            path = root_path / name
            if path.is_symlink():
                target = os.readlink(path)
                items.append(
                    {
                        "path": str(path.relative_to(base)),
                        "target": target,
                        "exists": path.exists(),
                    }
                )
    return items


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def build_report(base: Path) -> dict[str, Any]:
    required_files = {rel: (base / rel).exists() for rel in REQUIRED_FILES}
    required_dirs = {rel: (base / rel).is_dir() for rel in REQUIRED_DIRS}
    skill_files = {rel: (base / rel).exists() for rel in SKILL_FILES}
    symlinks = symlink_report(base)
    hardcoded_paths = scan_hardcoded_paths(base)
    collisions = case_collision_scan(base)
    health_command = resolve_health_command(base)
    health_rc, health_output = run(health_command, base)

    python_candidates = [
        base / ".venv" / "bin" / "python",
        base / ".venv" / "Scripts" / "python.exe",
    ]

    warnings: list[str] = []
    if any(item["path"] == "data" for item in symlinks):
        warnings.append("data is a symlink; on Windows, recreate it with mklink /D or use data_hdd_storage directly.")
    if hardcoded_paths:
        warnings.append("Hard-coded macOS volume paths remain; main entrypoint is portable, but some auxiliary tools are not.")
    if collisions:
        warnings.append("Case-insensitive filename collisions found; fix before copying to Windows.")
    if health_rc != 0:
        warnings.append("Health check failed; inspect health_output.")

    return {
        "workspace": str(base),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "python_candidates": {
            str(path.relative_to(base)): path.exists() for path in python_candidates
        },
        "required_files": required_files,
        "required_dirs": required_dirs,
        "skill_files": skill_files,
        "module_presence": {
            "webview": module_available("webview"),
            "openai": module_available("openai"),
            "anthropic": module_available("anthropic"),
            "google.genai": module_available("google.genai"),
            "groq": module_available("groq"),
            "langgraph": module_available("langgraph"),
            "chromadb": module_available("chromadb"),
        },
        "symlinks": symlinks,
        "case_collisions": collisions,
        "hardcoded_paths": hardcoded_paths[:200],
        "hardcoded_path_count": len(hardcoded_paths),
        "health_command": health_command,
        "health_rc": health_rc,
        "health_output": health_output,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit workspace portability")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--json-out", default="", help="Write JSON report")
    args = parser.parse_args()

    base = Path(args.workspace).expanduser().resolve()
    report = build_report(base)

    if args.json_out:
        out = Path(args.json_out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report: {out}")

    missing_files = [k for k, v in report["required_files"].items() if not v]
    missing_dirs = [k for k, v in report["required_dirs"].items() if not v]
    missing_skills = [k for k, v in report["skill_files"].items() if not v]

    print("== Portable Workspace Audit ==")
    print(f"Workspace: {report['workspace']}")
    print(f"Health command: {' '.join(report['health_command'])}")
    print(f"Health: {'OK' if report['health_rc'] == 0 else 'FAIL'}")
    print(f"Required files missing: {len(missing_files)}")
    print(f"Required dirs missing: {len(missing_dirs)}")
    print(f"Skill files missing: {len(missing_skills)}")
    print(f"Case collisions: {len(report['case_collisions'])}")
    print(f"Symlinks: {len(report['symlinks'])}")
    print(f"Hard-coded path hits: {report['hardcoded_path_count']}")

    for warning in report["warnings"]:
        print(f"[WARN] {warning}")

    return 1 if missing_files or missing_dirs or missing_skills or report["case_collisions"] or report["health_rc"] != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())


