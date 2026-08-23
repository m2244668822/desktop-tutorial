import tempfile
import unittest
from pathlib import Path

from core.encrypted_store import AESGCMJsonStore


class TrevorEdgeClientTests(unittest.TestCase):
    def test_failed_message_is_stored_only_in_encrypted_queue(self):
        from core.edge_client import EncryptedOfflineQueue, TrevorEdgeClient

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'offline_queue.json'
            queue = EncryptedOfflineQueue(path, AESGCMJsonStore(lambda: b'e' * 32))
            client = TrevorEdgeClient(
                'http://trevor.invalid',
                queue,
                api_key_provider=lambda: 'local-secret-key',
                sender=lambda *args, **kwargs: (_ for _ in ()).throw(OSError('offline')),
            )

            result = client.send_message({'message': '私人訊息'})
            raw = path.read_text(encoding='utf-8')

            self.assertEqual('queued_offline', result['status'])
            self.assertNotIn('私人訊息', raw)
            self.assertNotIn('local-secret-key', raw)
            self.assertEqual('AES-256-GCM', __import__('json').loads(raw)['algorithm'])

    def test_flush_replays_in_order_and_removes_successes(self):
        from core.edge_client import EncryptedOfflineQueue, TrevorEdgeClient

        with tempfile.TemporaryDirectory() as tmp:
            queue = EncryptedOfflineQueue(
                Path(tmp) / 'offline_queue.json',
                AESGCMJsonStore(lambda: b'q' * 32),
            )
            queue.enqueue('/api/send_message', {'message': '第一則'})
            queue.enqueue('/api/send_message', {'message': '第二則'})
            sent = []

            def sender(method, url, payload, headers):
                sent.append(payload['message'])
                return {'ok': True}

            client = TrevorEdgeClient(
                'http://trevor.invalid',
                queue,
                api_key_provider=lambda: 'local-secret-key',
                sender=sender,
            )
            result = client.flush()

            self.assertEqual(['第一則', '第二則'], sent)
            self.assertEqual(2, result['sent'])
            self.assertEqual([], queue.items())


if __name__ == '__main__':
    unittest.main()
