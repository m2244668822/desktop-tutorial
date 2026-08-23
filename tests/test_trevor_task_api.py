import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from core.data_paths import ProjectPaths
from core.web_server import WebServerMode


class _Store:
    def authenticate(self, api_key, *, required_scope):
        if api_key == 'valid' and required_scope in {'tasks', 'chat'}:
            return {'ok': True, 'key_id': 'task-key'}
        return {'ok': False, 'error': 'scope_denied'}


class _Bridge:
    def send_message(self, *args, **kwargs):
        return {'ok': True, 'reply': '收到', 'agent': 'trevor', 'role': '崔佛'}


class TrevorTaskApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        paths = ProjectPaths(root)
        mode = WebServerMode(_Bridge(), root, paths)
        self.mode = mode
        mode.api_key_store = _Store()
        self.data_root = paths.data
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), mode.get_handler({}, {}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def test_chat_archive_stays_under_external_data_root(self):
        self.assertTrue(self.mode._archive_dir.is_relative_to(self.data_root))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def _json(self, path, payload=None, *, authorized=True):
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['Authorization'] = 'Bearer valid'
        request = urllib_request.Request(
            self.base + path,
            data=None if payload is None else json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='GET' if payload is None else 'POST',
        )
        try:
            response = urllib_request.urlopen(request, timeout=3)
        except urllib_error.HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read().decode('utf-8'))
        with response:
            return response.status, json.loads(response.read().decode('utf-8'))

    def test_task_endpoint_enqueues_only_trevor_identity(self):
        status, payload = self._json(
            '/api/trevor/tasks',
            {
                'input': '修正語法',
                'category': 'bugfix',
                'capability_mode': 'coding',
                'priority': 2,
            },
        )

        self.assertEqual(202, status)
        self.assertEqual('trevor', payload['task']['agent'])
        self.assertEqual('崔佛', payload['task']['role'])
        self.assertNotIn('route', payload['task'])

    def test_invalid_task_limit_returns_bad_request(self):
        status, payload = self._json('/api/trevor/tasks?limit=not-a-number')

        self.assertEqual(400, status)
        self.assertEqual('invalid_limit', payload['error'])

    def test_send_message_marks_user_activity(self):
        status, _ = self._json(
            '/api/send_message',
            {'message': '你好', 'role': '崔佛'},
            authorized=False,
        )

        self.assertEqual(200, status)
        self.assertTrue((self.data_root / 'activity' / 'last_user_activity').exists())

    def test_required_auth_rejects_chat_without_chat_scope(self):
        self.mode.api_auth_required = True

        denied_status, denied = self._json(
            '/api/send_message',
            {'message': '遠端訊息', 'role': '崔佛'},
            authorized=False,
        )
        allowed_status, _ = self._json(
            '/api/send_message',
            {'message': '遠端訊息', 'role': '崔佛'},
            authorized=True,
        )

        self.assertEqual(401, denied_status)
        self.assertEqual('authentication_required', denied['error'])
        self.assertEqual(200, allowed_status)


if __name__ == '__main__':
    unittest.main()
