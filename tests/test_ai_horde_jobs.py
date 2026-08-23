import tempfile
import unittest
from pathlib import Path


class _InlineExecutor:
    def submit(self, function, *args):
        function(*args)


class _HoldingExecutor:
    def __init__(self):
        self.pending = []

    def submit(self, function, *args):
        self.pending.append((function, args))


class _Client:
    def __init__(self, statuses):
        self.statuses = list(statuses)

    def submit(self, kind, prompt, params):
        return 'provider-secret-id'

    def status(self, kind, provider_id):
        return self.statuses.pop(0)


class _Assets:
    def save_remote(self, url):
        return {
            'asset_id': '4dc061ef-5df6-4cc6-a2f0-c22db1c32793',
            'url': '/api/ai-horde/assets/4dc061ef-5df6-4cc6-a2f0-c22db1c32793',
            'alt': 'AI Horde 生成圖片',
            'width': 512,
            'height': 512,
        }


class AIHordeJobTests(unittest.TestCase):
    def test_text_job_completes_without_exposing_internal_values(self):
        from core.ai_horde_jobs import AIHordeJobManager

        client = _Client([{'done': True, 'generations': [{'text': '共享文字結果'}]}])
        manager = AIHordeJobManager(
            client,
            _Assets(),
            executor=_InlineExecutor(),
            sleep=lambda _seconds: None,
        )

        created = manager.create_job({'kind': 'text', 'prompt': '私人提示', 'params': {}})
        result = manager.get_job(created['job_id'])

        self.assertEqual('complete', result['state'])
        self.assertEqual('共享文字結果', result['reply'])
        self.assertEqual('trevor', result['agent'])
        self.assertNotIn('provider-secret-id', str(result))
        self.assertNotIn('私人提示', str(result))

    def test_image_job_replaces_remote_url_with_same_origin_asset(self):
        from core.ai_horde_jobs import AIHordeJobManager

        client = _Client(
            [{'done': True, 'generations': [{'img': 'https://images.example/result.png'}]}]
        )
        manager = AIHordeJobManager(
            client,
            _Assets(),
            executor=_InlineExecutor(),
            sleep=lambda _seconds: None,
        )

        created = manager.create_job({'kind': 'image', 'prompt': '城市', 'params': {}})
        result = manager.get_job(created['job_id'])

        self.assertEqual('complete', result['state'])
        self.assertEqual(1, len(result['images']))
        self.assertTrue(result['images'][0]['url'].startswith('/api/ai-horde/assets/'))
        self.assertNotIn('images.example', str(result))

    def test_bounded_queue_rejects_excess_jobs(self):
        from core.ai_horde_client import AIHordeError
        from core.ai_horde_jobs import AIHordeJobManager

        executor = _HoldingExecutor()
        manager = AIHordeJobManager(
            _Client([]),
            _Assets(),
            executor=executor,
            max_concurrent=1,
            max_queued=1,
        )
        manager.create_job({'kind': 'text', 'prompt': '一', 'params': {}})
        manager.create_job({'kind': 'text', 'prompt': '二', 'params': {}})

        with self.assertRaises(AIHordeError) as raised:
            manager.create_job({'kind': 'text', 'prompt': '三', 'params': {}})

        self.assertEqual('queue_full', raised.exception.code)


if __name__ == '__main__':
    unittest.main()
