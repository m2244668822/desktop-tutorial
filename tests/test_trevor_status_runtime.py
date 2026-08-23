import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


class TrevorStatusRuntimeTests(unittest.TestCase):
    @staticmethod
    def _server(data_root):
        from core.web_server import WebServerMode

        server = WebServerMode.__new__(WebServerMode)
        server.paths = SimpleNamespace(data=data_root)
        server.bridge = SimpleNamespace(monitor_active=False)
        server.readiness_payload = lambda: {
            'required_ready': True,
            'bridge_ready': True,
            'status': 'ready',
            'degraded_reasons': [],
        }
        server._tcp_up = lambda host, port: False
        return server

    def test_autonomy_status_uses_scheduler_and_worker_heartbeats(self):
        from core.web_server import WebServerMode

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            autonomy = data_root / 'autonomy'
            autonomy.mkdir()
            for name, mode in (
                ('scheduler_state.json', 'scheduler'),
                ('worker_state.json', 'worker'),
            ):
                (autonomy / name).write_text(
                    json.dumps(
                        {
                            'daemon_status': 'running',
                            'mode': mode,
                            'heartbeat_at': datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                    encoding='utf-8',
                )
            server = WebServerMode.__new__(WebServerMode)
            server.paths = SimpleNamespace(data=data_root)
            server.bridge = SimpleNamespace(monitor_active=False)
            server.readiness_payload = lambda: {
                'required_ready': True,
                'bridge_ready': True,
                'status': 'ready',
                'degraded_reasons': [],
            }
            server._tcp_up = lambda host, port: True

            payload = server.trevor_status_payload()

        self.assertTrue(payload['autonomy']['ready'])
        self.assertTrue(payload['autonomy']['scheduler']['ready'])
        self.assertTrue(payload['autonomy']['worker']['ready'])
        self.assertEqual(1, payload['autonomy']['max_concurrent_tasks'])

    def test_combined_daemon_reports_running_scheduler_and_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            autonomy = data_root / 'autonomy'
            autonomy.mkdir()
            heartbeat = datetime.now(timezone.utc).isoformat()
            (autonomy / 'daemon_state.json').write_text(
                json.dumps(
                    {
                        'daemon_status': 'running',
                        'mode': 'combined',
                        'heartbeat_at': heartbeat,
                    }
                ),
                encoding='utf-8',
            )
            server = self._server(data_root)

            payload = server.trevor_status_payload()

        scheduler = payload['autonomy']['scheduler']
        worker = payload['autonomy']['worker']
        self.assertTrue(scheduler['ready'])
        self.assertEqual('running', scheduler['status'])
        self.assertEqual('combined', scheduler['mode'])
        self.assertEqual('combined', scheduler['via'])
        self.assertTrue(worker['ready'])
        self.assertEqual('running', worker['status'])
        self.assertEqual('combined', worker['mode'])
        self.assertEqual('combined', worker['via'])

    def test_data_migration_distinguishes_device_and_graphiti_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            migrations = data_root / 'migrations'
            migrations.mkdir()
            (migrations / 'trevor_data_manifest.json').write_text(
                json.dumps({'unique_turns': 5424, 'conversation_threads': 1464}),
                encoding='utf-8',
            )
            server = self._server(data_root)

            payload = server.trevor_status_payload()

        migration = payload['data_migration']
        self.assertEqual('device_ready_graphiti_pending', migration['state'])
        self.assertTrue(migration['device']['ready'])
        self.assertEqual(5424, migration['device']['unique_turns'])
        self.assertFalse(migration['graphiti']['ready'])


if __name__ == '__main__':
    unittest.main()
