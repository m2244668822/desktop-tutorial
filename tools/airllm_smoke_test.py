#!/usr/bin/env python3
"""Smoke test for the isolated AirLLM runtime."""
from __future__ import annotations

import importlib.metadata as md
import platform
import signal
import sys


def _timeout(signum, frame):  # noqa: ARG001
    raise TimeoutError("AirLLM smoke test timed out")


def main() -> int:
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(60)
    try:
        print(f"python={sys.version.split()[0]}")
        print(f"machine={platform.machine()}")
        for name in ["airllm", "torch", "transformers", "optimum", "numpy", "huggingface-hub"]:
            print(f"{name}={md.version(name)}")
        from airllm import AirLLMBaseModel, AirLLMLlama2, AutoModel

        print(f"AutoModel={AutoModel.__name__}")
        print(f"AirLLMLlama2={AirLLMLlama2.__name__}")
        print(f"AirLLMBaseModel={AirLLMBaseModel.__name__}")
        print("airllm_smoke=ok")
        return 0
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
