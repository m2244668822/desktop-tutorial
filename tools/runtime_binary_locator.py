#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Iterable, Mapping


WhichCommand = Callable[[str], str | None]


def _clean(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _has_path_separator(value: str) -> bool:
    return any(sep and sep in value for sep in (os.sep, os.altsep, "/", "\\"))


def _existing_files(candidates: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    found: list[Path] = []
    for candidate in candidates:
        try:
            path = candidate.expanduser()
            key = str(path).casefold()
            if key in seen:
                continue
            seen.add(key)
            if path.exists() and path.is_file():
                found.append(path)
        except OSError:
            continue
    return found


def winget_package_binary_candidates(
    binary_name: str,
    *,
    env: Mapping[str, str] | os._Environ[str] = os.environ,
    package_markers: tuple[str, ...] = (),
) -> list[Path]:
    local_app_data = _clean(str(env.get("LOCALAPPDATA", "") or ""))
    if not local_app_data:
        return []
    package_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not package_root.exists():
        return []
    matches: list[Path] = []
    lowered_markers = tuple(marker.casefold() for marker in package_markers)
    for package_dir in package_root.iterdir():
        if lowered_markers and not any(marker in package_dir.name.casefold() for marker in lowered_markers):
            continue
        try:
            matches.extend(package_dir.rglob(binary_name))
        except OSError:
            continue
    return _existing_files(matches)


def ffmpeg_candidates(
    *,
    env: Mapping[str, str] | os._Environ[str] = os.environ,
) -> list[Path]:
    candidates: list[Path] = []
    for key in ("FFMPEG_PATH", "XIAOBIAN_FFMPEG_PATH"):
        raw = _clean(str(env.get(key, "") or ""))
        if raw and (_has_path_separator(raw) or Path(raw).is_absolute()):
            candidates.append(Path(raw))
    candidates.extend(
        winget_package_binary_candidates(
            "ffmpeg.exe",
            env=env,
            package_markers=("ffmpeg", "gyan"),
        )
    )
    return _existing_files(candidates)


def resolve_binary(
    name: str,
    *,
    explicit_path: str | None = None,
    env_keys: tuple[str, ...] = (),
    env: Mapping[str, str] | os._Environ[str] = os.environ,
    which: WhichCommand = shutil.which,
    candidates: Iterable[Path] = (),
) -> dict[str, object]:
    path_lookup = which(name) or ""
    env_checks: list[dict[str, object]] = []

    if explicit_path:
        raw = _clean(explicit_path)
        path = Path(raw).expanduser()
        exists = path.exists() and path.is_file()
        return {
            "found": exists,
            "source": "argument",
            "path": str(path) if exists else "",
            "configured_path": raw,
            "path_lookup": path_lookup,
            "env_checks": env_checks,
            "candidate_paths": [str(item) for item in _existing_files(candidates)],
            **({} if exists else {"error": "configured_path_not_found"}),
        }

    for key in env_keys:
        raw = _clean(str(env.get(key, "") or ""))
        if not raw:
            env_checks.append({"key": key, "value": "", "configured": False})
            continue
        if _has_path_separator(raw) or Path(raw).is_absolute():
            path = Path(raw).expanduser()
            exists = path.exists() and path.is_file()
            env_checks.append({"key": key, "value": raw, "configured": True, "exists": exists, "is_file": exists})
            return {
                "found": exists,
                "source": key,
                "path": str(path) if exists else "",
                "configured_path": raw,
                "path_lookup": path_lookup,
                "env_checks": env_checks,
                "candidate_paths": [str(item) for item in _existing_files(candidates)],
                **({} if exists else {"error": "configured_path_not_found"}),
            }
        resolved = which(raw)
        env_checks.append({"key": key, "value": raw, "configured": True, "exists": bool(resolved), "is_file": bool(resolved)})
        return {
            "found": bool(resolved),
            "source": key,
            "path": resolved or "",
            "configured_path": raw,
            "path_lookup": path_lookup,
            "env_checks": env_checks,
            "candidate_paths": [str(item) for item in _existing_files(candidates)],
            **({} if resolved else {"error": "configured_command_not_found"}),
        }

    if path_lookup:
        return {
            "found": True,
            "source": "PATH",
            "path": path_lookup,
            "configured_path": "",
            "path_lookup": path_lookup,
            "env_checks": env_checks,
            "candidate_paths": [str(item) for item in _existing_files(candidates)],
        }

    candidate_files = _existing_files(candidates)
    if candidate_files:
        return {
            "found": True,
            "source": "candidate",
            "path": str(candidate_files[0]),
            "configured_path": "",
            "path_lookup": "",
            "env_checks": env_checks,
            "candidate_paths": [str(item) for item in candidate_files],
        }

    return {
        "found": False,
        "source": "missing",
        "path": "",
        "configured_path": "",
        "path_lookup": "",
        "env_checks": env_checks,
        "candidate_paths": [],
    }


def resolve_ffmpeg(
    ffmpeg_path: str | None = None,
    *,
    env: Mapping[str, str] | os._Environ[str] = os.environ,
    which: WhichCommand = shutil.which,
) -> dict[str, object]:
    return resolve_binary(
        "ffmpeg",
        explicit_path=ffmpeg_path,
        env_keys=("FFMPEG_PATH", "XIAOBIAN_FFMPEG_PATH"),
        env=env,
        which=which,
        candidates=ffmpeg_candidates(env=env),
    )
