#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the adaptive neural hub."""

import tempfile
import unittest

from neural_hub import NeuroHub


class AdaptiveNeuralHubTests(unittest.TestCase):
    def test_adaptive_hub_initializes_and_reports_status(self):
        with tempfile.TemporaryDirectory() as data_dir:
            hub = NeuroHub(data_dir=data_dir, adaptive=True)
            status = hub.get_full_status()

        self.assertEqual("神經網絡中樞系統 (自適應成長)", status["system_name"])
        self.assertGreater(status["topology"]["total_neurons"], 0)
        self.assertGreater(status["topology"]["total_connections"], 0)
        self.assertGreaterEqual(status["topology"]["neuron_scale"], 1.0)
        self.assertGreaterEqual(status["topology"]["connection_boost"], 1.0)
        self.assertEqual(0, status["data_loaded"]["total_conversations"])
        self.assertIn("growth_summary", status)


if __name__ == "__main__":
    unittest.main()
