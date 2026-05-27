#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility shim for importing `NeuroHub` from the project root.

This keeps older scripts/tests that use `from neural_hub import NeuroHub`
working after the code was moved under `500/llama32-chat/learning/`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_impl_module():
    root = Path(__file__).resolve().parent
    impl = root / "500" / "llama32-chat" / "learning" / "neural_hub.py"
    if not impl.exists():
        raise ModuleNotFoundError(f"neural_hub implementation not found: {impl}")
    spec = importlib.util.spec_from_file_location("_neural_hub_impl", impl)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"unable to load neural_hub implementation: {impl}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_impl = _load_impl_module()

AnomalyReporter = _impl.AnomalyReporter
Neuron = _impl.Neuron
NeuronLayer = _impl.NeuronLayer
NeuroHub = _impl.NeuroHub

__all__ = ["AnomalyReporter", "Neuron", "NeuronLayer", "NeuroHub"]
