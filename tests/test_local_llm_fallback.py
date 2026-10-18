import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_health_probe_auto_selects_available_non_embedding_model(self):
        bridge = self._bridge()
        bridge._load_merged_env_data = lambda: {
            "OLLAMA_CHAT_URL": "http://127.0.0.1:11434/api/chat",
        }

        with patch(
            "desktop_chat_app.urllib_request.urlopen",
            return_value=_Response({"models": [{"name": "qwen2.5:1.5b"}]}),
        ):
            state = bridge._refresh_local_llm_health(force=True)

        self.assertTrue(state["healthy"])
        self.assertEqual("qwen2.5:1.5b", state["model"])
        self.assertEqual(["qwen2.5:1.5b"], state["available_models"])

    def test_health_probe_does_not_auto_select_embedding_model(self):
        bridge = self._bridge()
        bridge._load_merged_env_data = lambda: {
            "OLLAMA_CHAT_URL": "http://127.0.0.1:11434/api/chat",
        }

        with patch(
            "desktop_chat_app.urllib_request.urlopen",
            return_value=_Response({"models": [{"name": "nomic-embed-text:latest"}]}),
        ):
            state = bridge._refresh_local_llm_health(force=True)

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

    def test_desktop_bridge_orchestrated_chat_persists_local_result(self):
        from desktop_chat_app import DesktopBridge
        from core.provider_registry import ProviderRegistry

        class FakeTransport:
            def __init__(self):
                self.payloads = []

            def generate(self, provider, payload):
                self.payloads.append(payload)
                return "orchestrated local reply"

        with tempfile.TemporaryDirectory() as tmp:
            bridge = DesktopBridge.__new__(DesktopBridge)
            bridge.paths = SimpleNamespace(data=Path(tmp) / "data")
            bridge.provider_registry = ProviderRegistry(env={})
            bridge.provider_client = object()
            bridge.live_llm_timeout_sec = 3
            bridge.live_llm_max_tokens = 128
            bridge.live_llm_temperature = 0.2
            bridge.reply_counter = 1
            bridge.last_live_llm_meta = {}
            bridge._orchestrated_last_turn = {}
            bridge._load_merged_env_data = lambda: {}
            bridge._refresh_local_llm_health = lambda force=False: {
                "healthy": True,
                "model": "qwen2.5:1.5b",
            }
            bridge._local_llm_config = lambda: {
                "chat_url": "http://127.0.0.1:11434/api/chat",
                "model": "qwen2.5:1.5b",
            }
            bridge._build_live_llm_messages = lambda **kwargs: [
                {"role": "user", "content": kwargs["user_message"]}
            ]
            remembered = []
            bridge._remember_dialog_turn = lambda **kwargs: remembered.append(kwargs)

            local_transport = FakeTransport()
            bridge._orchestrated_last_turn["session-1"] = {
                "content": "cloud reply",
                "reasoning_details": [{"type": "reasoning.summary", "data": "opaque"}],
                "model_id": "nvidia/nemotron-3-ultra-550b-a55b:free",
            }
            with patch("desktop_chat_app.OllamaChatTransport", return_value=local_transport):
                result = bridge._run_orchestrated_chat(
                    message="hello",
                    role="申言者",
                    model_key="orchestrated",
                    retrieval_brief="",
                    capability_mode="general",
                    analysis={},
                    session_id="session-1",
                )

            self.assertTrue(result["ok"])
            self.assertEqual("orchestrated local reply", result["response"])
            self.assertEqual("qwen2.5:1.5b", result["model"])
            self.assertEqual("model_gateway", result["llm_live"]["transport"])
            self.assertEqual(1, len(remembered))
            self.assertTrue((Path(tmp) / "data" / "orchestrator" / "events.jsonl").exists())
            self.assertNotIn("reasoning_details", local_transport.payloads[0]["messages"][0])


if __name__ == "__main__":
    unittest.main()
