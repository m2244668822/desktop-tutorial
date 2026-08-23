import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


class TrevorStatusRuntimeTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
