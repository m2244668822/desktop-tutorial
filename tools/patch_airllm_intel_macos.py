#!/usr/bin/env python3
"""Patch AirLLM so Intel macOS does not import MLX-only modules at package import.

AirLLM 2.8.6+ treats every macOS host as MLX-capable. MLX is Apple Silicon only,
so Intel macOS needs the non-MLX imports that Linux/Windows use.
"""
from __future__ import annotations

import platform
import site
import sys
from pathlib import Path


def main() -> int:
    search_roots = [Path(p) for p in site.getsitepackages()]
    search_roots.extend(Path(p) for p in sys.path if p)
    package_dirs = [root / "airllm" for root in search_roots if (root / "airllm").is_dir()]
    package_dir = package_dirs[0] if package_dirs else None
    init_path = package_dir / "__init__.py" if package_dir else None
    if init_path is None:
        print("airllm package not found in this Python environment", file=sys.stderr)
        return 1

    original = init_path.read_text(encoding="utf-8")
    if "is_on_apple_silicon" in original and '{"arm64", "aarch64"}' in original:
        print(f"already patched: {init_path}")
    else:
        patched = '''from sys import platform\nimport platform as _platform\n\n_machine = _platform.machine().lower()\nis_on_apple_silicon = platform == "darwin" and _machine in {"arm64", "aarch64"}\n\nif is_on_apple_silicon:\n    from .airllm_llama_mlx import AirLLMLlamaMlx\n    from .auto_model import AutoModel\nelse:\n    from .airllm import AirLLMLlama2\n    from .airllm_chatglm import AirLLMChatGLM\n    from .airllm_qwen import AirLLMQWen\n    from .airllm_qwen2 import AirLLMQWen2\n    from .airllm_baichuan import AirLLMBaichuan\n    from .airllm_internlm import AirLLMInternLM\n    from .airllm_mistral import AirLLMMistral\n    from .airllm_mixtral import AirLLMMixtral\n    from .airllm_base import AirLLMBaseModel\n    from .auto_model import AutoModel\n    from .utils import split_and_save_layers\n    from .utils import NotEnoughSpaceException\n'''
        backup = init_path.with_suffix(".py.airllm-intel-backup")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        init_path.write_text(patched, encoding="utf-8")
        print(f"patched: {init_path}")

    auto_model_path = package_dir / "auto_model.py"
    auto_original = auto_model_path.read_text(encoding="utf-8")
    auto_patched = auto_original
    auto_patched = auto_patched.replace(
        'from sys import platform\n\nis_on_mac_os = False\n\nif platform == "darwin":\n    is_on_mac_os = True\n\nif is_on_mac_os:\n    from airllm import AirLLMLlamaMlx\n',
        'from sys import platform\nimport platform as _platform\n\n_machine = _platform.machine().lower()\nis_on_mac_os = platform == "darwin"\nis_on_apple_silicon = is_on_mac_os and _machine in {"arm64", "aarch64"}\n\nif is_on_apple_silicon:\n    from airllm import AirLLMLlamaMlx\n',
    )
    auto_patched = auto_patched.replace("if is_on_mac_os:", "if is_on_apple_silicon:")
    if auto_patched != auto_original:
        auto_backup = auto_model_path.with_suffix(".py.airllm-intel-backup")
        if not auto_backup.exists():
            auto_backup.write_text(auto_original, encoding="utf-8")
        auto_model_path.write_text(auto_patched, encoding="utf-8")
        print(f"patched: {auto_model_path}")

    print(f"machine={platform.machine()} python={sys.version.split()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
