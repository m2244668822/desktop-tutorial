import unittest
from pathlib import Path


class AIHordeFrontendContractTests(unittest.TestCase):
    def test_all_chat_templates_use_async_horde_jobs(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('chat.html', 'chat_shell.html', 'agent_shell.html', 'monitor_shell.html'):
            with self.subTest(template=name):
                source = (root / 'templates' / name).read_text(encoding='utf-8')
                self.assertIn('<option value="horde_text">共享文字</option>', source)
                self.assertIn('function isAIHordeMode(mode)', source)
                self.assertIn('async function runAIHordeJob(', source)
                self.assertIn('fetch("/api/ai-horde/jobs"', source)
                self.assertIn('`/api/ai-horde/jobs/${created.job_id}`', source)
                self.assertIn('img.src || img.url', source)
                self.assertIn('iMode === "image_generation" || iMode === "horde_text"', source)


if __name__ == '__main__':
    unittest.main()
