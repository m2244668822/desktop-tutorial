import json
import unittest
from unittest.mock import patch


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class LocalLLMFallbackTests(unittest.TestCase):
    def _bridge(self):
        from desktop_chat_app import DesktopBridge

        bridge = DesktopBridge.__new__(DesktopBridge)
        bridge.local_llm_state = {
            "healthy": False,
            "service_alive": False,
            "model_available": False,
            "model": "",
            "available_models": [],
            "latency_ms": None,
            "last_checked_at": 0.0,
            "failure_reason": "not_checked",
        }
        bridge.oss_is_healthy = False
        bridge.oss_health_check_interval = 30
        bridge.last_oss_health_check = 0
        bridge.live_llm_timeout_sec = 3
        bridge._load_merged_env_data = lambda: {
            "OLLAMA_CHAT_URL": "http://127.0.0.1:11434/api/chat",
            "OPEN_SOURCE_CHAT_MODEL": "qwen2.5:7b",
        }
        return bridge

    def test_health_probe_marks_local_model_ready(self):
        bridge = self._bridge()

        with patch(
            "desktop_chat_app.urllib_request.urlopen",
            return_value=_Response({"models": [{"name": "qwen2.5:7b"}]}),
        ):
            state = bridge._refresh_local_llm_health(force=True)

        self.assertTrue(state["service_alive"])
        self.assertTrue(state["model_available"])
        self.assertTrue(state["healthy"])
        self.assertTrue(bridge.oss_is_healthy)
        self.assertEqual("", state["failure_reason"])

    def test_health_probe_reports_missing_model(self):
        bridge = self._bridge()

        with patch(
            "desktop_chat_app.urllib_request.urlopen",
            return_value=_Response({"models": [{"name": "tinyllama:latest"}]}),
        ):
            state = bridge._refresh_local_llm_health(force=True)

        self.assertTrue(state["service_alive"])
        self.assertFalse(state["model_available"])
        self.assertFalse(state["healthy"])
        self.assertEqual("model_missing", state["failure_reason"])

    def test_explicit_cloud_failure_can_recover_to_local(self):
        bridge = self._bridge()
        bridge.enable_live_llm_default = True
        bridge._normalize_deliberation_mode = lambda value: value
        bridge._build_live_llm_messages = lambda **_kwargs: [{"role": "user", "content": "hi"}]
        bridge._call_ollama_chat = lambda _messages: (
            "本機回覆",
            {
                "ok": True,
                "transport": "ollama",
                "provider": "open_source",
                "model": "qwen2.5:7b",
            },
        )

        reply, meta = bridge._generate_live_llm_reply(
            message="測試",
            role="申言者",
            requested_backend="open_source",
            retrieval_brief="",
            capability_mode="general",
            deliberation="fast",
        )

        self.assertEqual("本機回覆", reply)
        self.assertTrue(meta["ok"])
        self.assertEqual("ollama", meta["transport"])
        self.assertEqual("qwen2.5:7b", meta["model"])


if __name__ == "__main__":
    unittest.main()
