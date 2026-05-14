#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified web entrypoint for this repository.

Mainline command:
    python3 desktop_chat_app.py --web-server --host 127.0.0.1 --port 5001

This wrapper delegates runtime to chatgpt_server.py while enforcing a single
startup path and consistent host/port env configuration.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
BACKEND_FILE = BASE_DIR / "chatgpt_server.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Desktop Chat App unified entrypoint")
    parser.add_argument(
        "--web-server",
        action="store_true",
        help="Run backend in web server mode (default behavior).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=5001, help="Bind port.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode in delegated backend.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(2, min(8, os.cpu_count() or 2)),
        help="Gunicorn worker processes (SMP). Minimum is 2.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Threads per Gunicorn worker.",
    )
    parser.add_argument("--timeout", type=int, default=120, help="Gunicorn timeout seconds.")
    parser.add_argument(
        "--graceful-timeout",
        type=int,
        default=30,
        help="Gunicorn graceful-timeout seconds.",
    )
    parser.add_argument("--keep-alive", type=int, default=5, help="Gunicorn keep-alive seconds.")
    parser.add_argument(
        "--max-requests",
        type=int,
        default=2000,
        help="Gunicorn max requests before worker recycle.",
    )
    parser.add_argument(
        "--max-requests-jitter",
        type=int,
        default=200,
        help="Gunicorn max-requests jitter.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not BACKEND_FILE.exists():
        print(f"❌ 找不到後端檔案: {BACKEND_FILE}")
        return 1

    # Standardize runtime env so all launchers share one source of truth.
    os.environ["CHAT_SERVER_HOST"] = str(args.host)
    os.environ["CHAT_SERVER_PORT"] = str(args.port)
    os.environ["CHAT_MAINLINE_ENTRY"] = "desktop_chat_app.py"
    os.environ["STARTUP_LEADER_ONLY"] = "true"
    if args.debug:
        os.environ["DEBUG_MODE"] = "true"

    # Always enforce SMP: at least 2 worker processes.
    workers = max(2, int(args.workers or 2))
    threads = max(1, int(args.threads or 1))
    timeout = max(30, int(args.timeout or 120))
    graceful_timeout = max(10, int(args.graceful_timeout or 30))
    keep_alive = max(1, int(args.keep_alive or 5))
    max_requests = max(200, int(args.max_requests or 2000))
    max_requests_jitter = max(0, int(args.max_requests_jitter or 200))

    # Ensure module resolution works regardless of current cwd.
    os.chdir(str(BASE_DIR))

    try:
        __import__("gunicorn")
    except Exception:
        print("⚠️ 未安裝 gunicorn，正在自動安裝...")
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "gunicorn"])
        if rc != 0:
            print("❌ gunicorn 安裝失敗，無法啟動 SMP。")
            return rc

    bind = f"{args.host}:{args.port}"
    print(f"🚀 SMP 啟動：Gunicorn @ {bind} | workers={workers} threads={threads}")
    gunicorn_cmd = [
        sys.executable,
        "-m",
        "gunicorn",
        "chatgpt_server:app",
        "--bind",
        bind,
        "--workers",
        str(workers),
        "--worker-class",
        "gthread",
        "--threads",
        str(threads),
        "--timeout",
        str(timeout),
        "--graceful-timeout",
        str(graceful_timeout),
        "--keep-alive",
        str(keep_alive),
        "--max-requests",
        str(max_requests),
        "--max-requests-jitter",
        str(max_requests_jitter),
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
        "--log-level",
        "info",
    ]
    os.execv(sys.executable, gunicorn_cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
