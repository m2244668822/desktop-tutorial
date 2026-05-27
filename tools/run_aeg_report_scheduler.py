#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.workflow_runtime import build_tool_registry
from tools.write_aeg_shared_report import main as write_aeg_report


def run_once(limit: int = 120) -> int:
    spec = build_tool_registry().get("aeg_keyword_graph")
    if spec is None:
        print(json.dumps({"ok": False, "error": "tool_missing:aeg_keyword_graph"}, ensure_ascii=False))
        return 1

    output = spec.handler(ROOT, {"limit": max(20, int(limit))})
    ok, note = spec.verifier(output)
    print(
        json.dumps(
            {
                "ok": bool(ok),
                "note": note,
                "output": output,
            },
            ensure_ascii=False,
        )
    )
    rc_report = write_aeg_report()
    return 0 if ok and rc_report == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=300, help="Cycle interval seconds (min 30)")
    ap.add_argument("--once", action="store_true", help="Run one cycle and exit")
    ap.add_argument("--limit", type=int, default=120, help="Top keyword/edge limit")
    args = ap.parse_args()

    if args.once:
        return run_once(limit=args.limit)

    interval = max(30, int(args.interval))
    while True:
        rc = run_once(limit=args.limit)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] aeg scheduler cycle rc={rc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
