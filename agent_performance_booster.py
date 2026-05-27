#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent performance booster compatibility layer.

Provides `AgentPerformanceBoost` expected by `agent_brain_dashboard.py`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent


class AgentPerformanceBoost:
    """Bridge class that delegates to the optimization analyzer."""

    def __init__(self) -> None:
        self.base_dir = BASE_DIR

    def generate_performance_report(self) -> dict[str, Any]:
        """Generate and return performance report.

        Falls back to a minimal report when optimization module is unavailable.
        """
        try:
            from agent_performance_optimization import analyze_sessions

            result = analyze_sessions()
            if isinstance(result, dict):
                return result
        except Exception as exc:
            return {
                "timestamp": datetime.now().isoformat(),
                "status": "degraded",
                "error": str(exc),
            }

        return {
            "timestamp": datetime.now().isoformat(),
            "status": "ok",
            "message": "report generated",
        }


if __name__ == "__main__":
    report = AgentPerformanceBoost().generate_performance_report()
    print("✅ AgentPerformanceBoost report ready")
    print(report)
