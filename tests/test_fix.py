#!/usr/bin/env python3
"""Regression tests for ChatGPT database loading limits."""

import time
import tempfile
import unittest
from pathlib import Path

from tests.chatgpt_fixture import create_chatgpt_fixture
from tools.local_memory_api import LocalMemoryAPI


def _chatgpt_conversations(conversations):
    return [item for item in conversations if item.get("source") == "chatgpt_database"]


class ChatGPTDatabaseLoadingTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        create_chatgpt_fixture(self.root)

    def test_default_limit_loads_first_100_chatgpt_conversations(self):
        api = LocalMemoryAPI(base_dir=self.root, chatgpt_limit=100)
        conversations = api.get_all_conversations()

        self.assertEqual(100, len(_chatgpt_conversations(conversations)))
        self.assertGreaterEqual(len(conversations), 100)

    def test_custom_limit_loads_requested_chatgpt_count(self):
        api = LocalMemoryAPI(base_dir=self.root, chatgpt_limit=50)
        conversations = api.get_all_conversations()

        self.assertEqual(50, len(_chatgpt_conversations(conversations)))
        self.assertGreaterEqual(len(conversations), 50)

    def test_full_load_expands_past_default_limit_with_acceptable_latency(self):
        start = time.time()
        api = LocalMemoryAPI(base_dir=self.root, chatgpt_limit=None)
        conversations = api.get_all_conversations()
        elapsed = time.time() - start

        chatgpt_items = _chatgpt_conversations(conversations)
        self.assertGreaterEqual(len(chatgpt_items), 1000)
        self.assertGreater(len(conversations), len(chatgpt_items))
        self.assertLess(elapsed, 30)


if __name__ == "__main__":
    unittest.main()
