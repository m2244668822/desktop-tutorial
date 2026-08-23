#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Start a long-running command detached from the caller's process group.

This helper keeps Perob services alive when they are started from terminals or
agent shells that clean up their child process group after the command exits.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a detached background command")
    parser.add_argument("--cwd", required=True, help="Working directory for the child process")
    parser.add_argument("--pidfile", required=True, help="Where to write the child PID")
    parser.add_argument("--stdout", required=True, help="File path for stdout")
    parser.add_argument("--stderr", required=True, help="File path for stderr")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Extra environment assignment, e.g. KEY=VALUE. Can be repeated.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command after --")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command after --")
    return args


def main() -> int:
    args = parse_args()
    cwd = Path(args.cwd).expanduser().resolve()
    pidfile = Path(args.pidfile).expanduser()
    stdout_path = Path(args.stdout).expanduser()
    stderr_path = Path(args.stderr).expanduser()
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    for item in args.env:
        if "=" not in item:
            print(f"invalid --env value: {item!r}", file=sys.stderr)
            return 2
        key, value = item.split("=", 1)
        env[key] = value

    with stdout_path.open("ab", buffering=0) as stdout_fh, stderr_path.open("ab", buffering=0) as stderr_fh:
        process = subprocess.Popen(
            args.command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout_fh,
            stderr=stderr_fh,
            start_new_session=True,
            close_fds=True,
        )
    pidfile.write_text(f"{process.pid}\n", encoding="utf-8")
    print(process.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
