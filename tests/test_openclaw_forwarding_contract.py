import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from core.openclaw_adapter import OpenClawAdapter


class _DummySocket:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False


class OpenClawForwardingContractTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(
            os.environ,
            {
                "OPENCLAW_ENABLED": "true",
                "OPENCLAW_GATEWAY_TOKEN": "test-token",
                "OPENCLAW_GATEWAY_HOST": "127.0.0.1",
                "OPENCLAW_GATEWAY_PORT": "18789",
                "OPENCLAW_TASK_ENDPOINT": "",
                "OPENCLAW_BIN": "/bin/echo",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_status_reports_websocket_forwarding_when_gateway_and_token_exist(self):
        with tempfile.TemporaryDirectory() as td, mock.patch("socket.create_connection", return_value=_DummySocket()):
            status = OpenClawAdapter(td).status()
        self.assertTrue(status["ok"])
        self.assertEqual(status["forwarding_mode"], "websocket")
        self.assertTrue(status["cli_forwarding_available"])
        self.assertTrue(status["websocket_forwarding_available"])
        self.assertTrue(status["task_forwarding_configured"])
        self.assertIn("last_forward_at", status)
        self.assertIn("last_forward_error", status)

    def test_forward_task_uses_official_gateway_cli_before_raw_websocket(self):
        with tempfile.TemporaryDirectory() as td, mock.patch("socket.create_connection", return_value=_DummySocket()):
            adapter = OpenClawAdapter(td)
            adapter._forward_via_cli_agent = lambda payload: {"ok": True, "route": "openclaw_websocket_cli", "response": {"content": "ok"}}
            adapter._forward_via_websocket = mock.Mock()
            result = adapter.forward_task({"message": "修 bug", "role": "工程師"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["route"], "openclaw_websocket_cli")
        adapter._forward_via_websocket.assert_not_called()

    def test_forward_task_falls_back_to_raw_websocket_when_cli_fails(self):
        with tempfile.TemporaryDirectory() as td, mock.patch("socket.create_connection", return_value=_DummySocket()):
            adapter = OpenClawAdapter(td)
            adapter._forward_via_cli_agent = lambda payload: {"ok": False, "error": "cli_failed"}
            adapter._forward_via_websocket = lambda payload: {"ok": True, "route": "openclaw_websocket", "response": {"content": "ok"}}
            result = adapter.forward_task({"message": "修 bug", "role": "工程師"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["route"], "openclaw_websocket")

    def test_raw_websocket_connect_challenge_is_not_a_successful_task(self):
        class FakeWs:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def send(self, _payload):
                return None
            def recv(self, timeout=None):
                return '{"type":"event","event":"connect.challenge","payload":{"nonce":"n"}}'

        fake_client = types.ModuleType("websockets.sync.client")
        fake_client.connect = lambda *args, **kwargs: FakeWs()
        fake_sync = types.ModuleType("websockets.sync")
        fake_websockets = types.ModuleType("websockets")
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            sys.modules,
            {
                "websockets": fake_websockets,
                "websockets.sync": fake_sync,
                "websockets.sync.client": fake_client,
            },
        ):
            result = OpenClawAdapter(td)._forward_via_websocket({"message": "修 bug"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "openclaw_handshake_not_completed")


if __name__ == "__main__":
    unittest.main()
