#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility shim for legacy self-learning entrypoint.

Older scripts import/execute `agent_self_learning.py`.
Current implementation was moved to `agent_self_learning_upgraded.py`.
This shim preserves the old module path and command behavior.
"""

from __future__ import annotations

import traceback


def main() -> int:
    try:
        from agent_self_learning_upgraded import AgentSelfLearningEnhanced

        learner = AgentSelfLearningEnhanced()
        learner.advanced_analyze()
        return 0
    except Exception as exc:  # pragma: no cover - defensive compatibility path
        print(f"[WARN] 自主學習升級模組執行失敗: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        # Keep compatibility path non-fatal for launcher/import checks.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

