#!/usr/bin/env python3
"""Regression tests for mid-term LocalMemoryAPI improvements."""

import time
import tempfile
import unittest
from pathlib import Path

from tests.chatgpt_fixture import create_chatgpt_fixture
from tools.local_memory_api import LocalMemoryAPI


class MidTermLocalMemoryAPITests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        create_chatgpt_fixture(self.root)
        self.api = LocalMemoryAPI(base_dir=self.root, chatgpt_limit=100)

    def test_paginated_loading_returns_metadata_and_cached_results(self):
        page1 = self.api.get_conversations_paginated(page=1, page_size=20)
        page1_cached = self.api.get_conversations_paginated(page=1, page_size=20)
        page2 = self.api.get_conversations_paginated(page=2, page_size=20)

        self.assertEqual(1, page1["pagination"]["page"])
        self.assertEqual(20, page1["pagination"]["page_size"])
        self.assertGreaterEqual(page1["pagination"]["total_items"], 20)
        self.assertTrue(page1["pagination"]["has_next"])
        self.assertEqual(20, len(page1["data"]))
        self.assertEqual(page1, page1_cached)
        self.assertEqual(20, len(page2["data"]))

    def test_search_auto_expand_and_cache(self):
        results = self.api.search_conversations(query="履歷", limit=10, auto_expand=True)
        cached = self.api.search_conversations(query="履歷", limit=10)

        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 10)
        self.assertEqual(results, cached)

    def test_cache_stats_and_targeted_clear(self):
        self.api.get_conversations_paginated(page=1, page_size=20)
        self.api.search_conversations(query="履歷", limit=10)

        stats = self.api.get_cache_stats()
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)
        self.assertGreaterEqual(stats["cached_items"]["paginated"], 1)
        self.assertGreaterEqual(stats["cached_items"]["search"], 1)

        clear_result = self.api.clear_cache("search")
        after = self.api.get_cache_stats()
        self.assertTrue(
            any(item.startswith("search") for item in clear_result["cleared"])
        )
        self.assertEqual(0, after["cached_items"]["search"])

    def test_statistics_dashboard_contains_expected_sections(self):
        dashboard = self.api.get_statistics_dashboard()

        self.assertGreaterEqual(dashboard["overview"]["total_conversations_loaded"], 100)
        self.assertGreater(dashboard["overview"]["total_messages"], 0)
        self.assertGreater(dashboard["overview"]["data_sources_count"], 0)
        self.assertIn("by_source", dashboard)
        self.assertIn("message_analysis", dashboard)
        self.assertIn("data_quality", dashboard)
        self.assertIn("cache_performance", dashboard)

    def test_common_operations_remain_responsive(self):
        self.api.get_all_conversations()
        operations = [
            lambda: self.api.get_latest_conversations(10),
            lambda: self.api.get_conversations_paginated(1, 50),
            lambda: self.api.search_conversations("對話", limit=5),
            lambda: self.api.get_memory_summary(),
        ]

        for operation in operations:
            with self.subTest(operation=operation):
                start = time.time()
                result = operation()
                elapsed = time.time() - start

                self.assertIsNotNone(result)
                self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
