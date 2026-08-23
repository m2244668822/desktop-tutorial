#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


BASE_DIR = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.data_paths import is_link_like, resolve_data_root
from core.llm_cns import llm_snapshot


@dataclass
class CheckResult:
    name: str
    ok: bool
    status: str
    detail: dict[str, Any]


def _run(cmd: list[str], cwd: Path | None = None, timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _which_candidates(name: str) -> list[str]:
    paths: list[str] = []
    hit = shutil.which(name)
    if hit:
        paths.append(str(Path(hit).resolve()))
    if os.name == "nt":
        probe = _run(["where.exe", name], timeout=3)
        if probe.returncode == 0:
            for row in (probe.stdout or "").splitlines():
                row = row.strip()
                if row and row not in paths:
                    paths.append(row)
    return paths


def _check_python() -> CheckResult:
    python_exe = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        return CheckResult("python_venv", False, "missing", {"expected": str(python_exe)})
    ver = _run([str(python_exe), "--version"], timeout=4)
    version = (ver.stdout or ver.stderr or "").strip()
    modules = {}
    for name in ("webview", "langgraph", "langchain", "chromadb", "sentence_transformers"):
        modules[name] = importlib.util.find_spec(name) is not None
    ok = ver.returncode == 0 and all(modules.values())
    return CheckResult(
        "python_venv",
        ok,
        "ready" if ok else "degraded",
        {"python": version, "modules": modules},
    )


def _check_data_root() -> CheckResult:
    data_root = resolve_data_root(BASE_DIR)
    data_path = BASE_DIR / "data"
    detail = {
        "data_path_exists": data_path.exists(),
        "data_path_is_dir": data_path.is_dir(),
        "data_path_is_link_like": is_link_like(data_path) if data_path.exists() else False,
        "resolved_data_root": str(data_root),
        "resolved_data_root_exists": data_root.exists(),
    }
    ok = data_root.exists()
    if not data_path.exists():
        status = "fallback_only"
    elif data_path.is_dir() or is_link_like(data_path):
        status = "linked_or_dir"
    else:
        status = "degraded"
    return CheckResult("data_root", ok, status, detail)


def _check_git() -> CheckResult:
    paths = _which_candidates("git")
    ver = _run(["git", "--version"], timeout=4)
    status_probe = _run(["git", "status", "--short"], cwd=BASE_DIR, timeout=6)
    healthy = _run(["git", "rev-parse", "--verify", "HEAD"], cwd=BASE_DIR, timeout=4)
    status = "ready"
    detail: dict[str, Any] = {
        "git_paths": paths,
        "git_version": (ver.stdout or ver.stderr or "").strip(),
        "status_returncode": status_probe.returncode,
        "head_ok": healthy.returncode == 0,
    }
    merged = "\n".join(
        part for part in ((status_probe.stdout or ""), (status_probe.stderr or "")) if part
    ).lower()
    corrupt = any(
        token in merged
        for token in (
            "object file",
            "invalid sha1 pointer",
            "invalid reflog entry",
            "missing blob",
            "fatal: bad object",
        )
    )
    if healthy.returncode != 0 or status_probe.returncode != 0 or corrupt:
        status = "metadata_corrupt"
        detail["head_error"] = (healthy.stderr or healthy.stdout or "").strip()[:500]
        detail["status_error"] = (status_probe.stderr or status_probe.stdout or "").strip()[:500]
    ok = ver.returncode == 0 and not (healthy.returncode != 0 or status_probe.returncode != 0 or corrupt)
    return CheckResult("git", ok, status, detail)


def _check_ollama() -> CheckResult:
    cmd = _run(["ollama", "--version"], timeout=4)
    base_url = "http://127.0.0.1:11434"
    ping_ok = False
    ping_error = ""
    try:
        with urllib_request.urlopen(
            urllib_request.Request(f"{base_url}/api/tags", method="GET"), timeout=2.0
        ):
            ping_ok = True
    except urllib_error.URLError as exc:
        ping_error = str(exc.reason)
    except Exception as exc:  # noqa: BLE001
        ping_error = str(exc)
    ok = cmd.returncode == 0 and ping_ok
    return CheckResult(
        "ollama",
        ok,
        "ready" if ok else "degraded",
        {
            "version": (cmd.stdout or cmd.stderr or "").strip(),
            "reachable": ping_ok,
            "error": ping_error,
        },
    )


def _check_llm() -> CheckResult:
    try:
        snap = llm_snapshot(BASE_DIR)
    except Exception as exc:
        return CheckResult("llm", False, "error", {"error": str(exc)})
    key_state = str(snap.get("key_state", "missing"))
    model = str(snap.get("model", "")).strip()
    open_source_model = str(snap.get("open_source_model", "")).strip()
    ok = key_state not in {"missing", "placeholder"} and bool(model)
    if not ok and open_source_model and open_source_model != "missing":
        ok = True
    return CheckResult(
        "llm",
        ok,
        "ready" if ok else "degraded",
        {
            "key_state": key_state,
            "model": model,
            "open_source_model": open_source_model,
            "base_url": snap.get("base_url", ""),
            "key_source": snap.get("key_source", ""),
        },
    )


def _find_node_install() -> tuple[str, str]:
    node_paths = _which_candidates("node")
    local = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe"
    )
    best = ""
    if local.exists():
        for item in sorted(local.rglob("node.exe")):
            best = str(item)
            break
    resolved = best or (node_paths[0] if node_paths else "")
    return resolved, "\n".join(node_paths)


def _check_node_n8n() -> CheckResult:
    node_path, all_nodes = _find_node_install()
    if not node_path:
        return CheckResult("node_n8n", False, "missing_node", {"node_paths": all_nodes})

    node_ver = _run([node_path, "--version"], timeout=4)
    node_dir = str(Path(node_path).parent)
    n8n_cmd = str(Path(node_dir) / "n8n.cmd")
    n8n_ok = Path(n8n_cmd).exists()
    n8n_ver = ""
    if n8n_ok:
        got = _run([n8n_cmd, "--version"], timeout=6)
        n8n_ok = got.returncode == 0
        n8n_ver = (got.stdout or got.stderr or "").strip()

    shadowed = "OpenAI.Codex" in all_nodes and node_path not in all_nodes.splitlines()[0]
    ok = node_ver.returncode == 0 and n8n_ok
    status = "ready" if ok else ("missing_n8n" if node_ver.returncode == 0 else "missing_node")
    if shadowed:
        status = f"{status}_with_shadowed_node"
    return CheckResult(
        "node_n8n",
        ok,
        status,
        {
            "node_selected": node_path,
            "node_version": (node_ver.stdout or node_ver.stderr or "").strip(),
            "node_candidates": all_nodes,
            "n8n_cmd": n8n_cmd,
            "n8n_version": n8n_ver,
        },
    )


def _check_n8n_spec() -> CheckResult:
    spec = BASE_DIR / "docs" / "superpowers" / "specs" / "n8n-workflow-xiaobian-video.json"
    if not spec.exists():
        return CheckResult("n8n_spec", False, "missing", {"path": str(spec)})
    try:
        payload = json.loads(spec.read_text(encoding="utf-8"))
        nodes = payload.get("nodes", [])
        return CheckResult(
            "n8n_spec",
            True,
            "ready",
            {"path": str(spec), "node_count": len(nodes)},
        )
    except Exception as exc:
        return CheckResult("n8n_spec", False, "invalid_json", {"path": str(spec), "error": str(exc)})


def _check_aeg() -> CheckResult:
    try:
        import core.langgraph_workflow as lg  # noqa: PLC0415

        available = bool(getattr(lg, "LANGGRAPH_AVAILABLE", False))
        has_run = hasattr(lg, "run_workflow")
        return CheckResult(
            "aeg_langgraph",
            available and has_run,
            "ready" if (available and has_run) else "degraded",
            {"langgraph_available": available, "run_workflow": has_run},
        )
    except Exception as exc:
        return CheckResult("aeg_langgraph", False, "error", {"error": str(exc)})


def _check_main_runtime() -> CheckResult:
    py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        return CheckResult("main_runtime", False, "missing_venv", {"python": str(py)})
    proc = _run([str(py), "system_main.py", "health"], cwd=BASE_DIR, timeout=60)
    ok = proc.returncode == 0
    return CheckResult(
        "main_runtime",
        ok,
        "ready" if ok else "failed",
        {
            "returncode": proc.returncode,
            "output_head": (proc.stdout or proc.stderr or "").splitlines()[:30],
        },
    )


def _missing_programs(results: list[CheckResult]) -> list[str]:
    missing: list[str] = []
    by_name = {item.name: item for item in results}
    if not by_name["python_venv"].ok:
        missing.append("python_venv_requirements")
    if not by_name["node_n8n"].ok:
        missing.append("node_or_n8n")
    if not by_name["git"].ok:
        missing.append("git_repo_recovery")
    if not by_name["ollama"].ok:
        missing.append("ollama_service")
    return missing


def run_harmony_check() -> dict[str, Any]:
    checks = [
        _check_python(),
        _check_data_root(),
        _check_main_runtime(),
        _check_git(),
        _check_node_n8n(),
        _check_n8n_spec(),
        _check_ollama(),
        _check_llm(),
        _check_aeg(),
    ]
    ok = all(item.ok for item in checks if item.name not in {"git"})
    # git corruption is tracked separately because runtime can continue in degraded mode.
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "workspace": str(BASE_DIR),
        "overall_ok": ok,
        "checks": [asdict(item) for item in checks],
        "missing_programs": _missing_programs(checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Main/CNS/n8n/git/AEG/LLM harmony check")
    parser.add_argument("--json-out", default="", help="Optional output JSON path")
    args = parser.parse_args()

    report = run_harmony_check()
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.json_out:
        out = Path(args.json_out).expanduser()
        if not out.is_absolute():
            out = BASE_DIR / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output + "\n", encoding="utf-8")
    return 0 if report.get("overall_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


