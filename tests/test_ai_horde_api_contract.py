import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request as urllib_request

from core.data_paths import ProjectPaths
from core.web_server import WebServerMode


class _Bridge:
    pass


class _Client:
    def public_status(self):
        return {
            'ok': True,
            'enabled': True,
            'configured': True,
            'key_source': 'keychain',
            'supports': ['image', 'text'],
        }


class _Jobs:
    def create_job(self, payload):
        return {
            'ok': True,
            'job_id': 'd8efdddb-d618-4133-a9f2-35cf3a17cb02',
            'state': 'queued',
            'poll_after_ms': 2000,
        }

    def get_job(self, job_id):
        return {
            'ok': True,
            'job_id': job_id,
            'state': 'complete',
            'agent': 'trevor',
            'role': '崔佛',
            'reply': '共享文字結果',
            'images': [],
        }


class _Assets:
    def read_asset(self, asset_id):
        if asset_id == '4dc061ef-5df6-4cc6-a2f0-c22db1c32793':
            return b'png-body', 'image/png'
        return None


class AIHordeApiContractTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        mode = WebServerMode(_Bridge(), root, ProjectPaths(root))
        mode.ai_horde_client = _Client()
        mode.ai_horde_jobs = _Jobs()
        mode.ai_horde_assets = _Assets()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), mode.get_handler({}, {}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _json(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib_request.Request(
            self.base + path,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='GET' if payload is None else 'POST',
        )
        with urllib_request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode('utf-8'))

    def test_status_create_and_poll_contract(self):
        status_code, status = self._json('/api/ai-horde/status')
        create_code, created = self._json(
            '/api/ai-horde/jobs', {'kind': 'text', 'prompt': '測試', 'params': {}}
        )
        poll_code, result = self._json('/api/ai-horde/jobs/' + created['job_id'])

        self.assertEqual(200, status_code)
        self.assertTrue(status['configured'])
        self.assertEqual('keychain', status['key_source'])
        self.assertEqual(202, create_code)
        self.assertEqual(200, poll_code)
        self.assertEqual('trevor', result['agent'])
        self.assertNotIn('apikey', json.dumps([status, created, result]).lower())

    def test_asset_response_has_private_security_headers(self):
        request = urllib_request.Request(
            self.base + '/api/ai-horde/assets/4dc061ef-5df6-4cc6-a2f0-c22db1c32793'
        )
        with urllib_request.urlopen(request, timeout=3) as response:
            body = response.read()

        self.assertEqual(b'png-body', body)
        self.assertEqual('nosniff', response.headers['X-Content-Type-Options'])
        self.assertEqual('private, max-age=3600', response.headers['Cache-Control'])


if __name__ == '__main__':
    unittest.main()
