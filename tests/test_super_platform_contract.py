import tempfile
import unittest
from pathlib import Path


class _FakeBridge:
    is_ready = True
    reply_counter = 0

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def _knowledge_status_summary(self):
        return {
            "ok": True,
            "sqlite_ready": True,
            "faiss_ready": False,
            "total_items": 3,
        }

    def get_memory_autosave_status(self):
        return {"ok": True, "state": "clean"}

    def get_aeg_training_status(self):
        return {"ok": True, "state": "ready"}

    def get_status(self):
        return {"ok": True}

    def get_api_onboarding_info(self):
        return {
            "providers": {
                "provider_catalog": [
                    {"key": "groq", "classification": {"tier": "enabled"}}
                ]
            }
        }


class SuperPlatformContractTests(unittest.TestCase):
    def test_capability_registry_uses_trevor_provider_truth_and_single_owner(self):
        from core.capability_registry import build_capability_registry

        with tempfile.TemporaryDirectory() as td:
            registry = build_capability_registry(
                td,
                provider_status={
                    "providers": [
                        {
                            "provider": "nvidia",
                            "label": "NVIDIA NIM",
                            "model": "nvidia/control",
                            "enabled": True,
                            "health": "available",
                        }
                    ]
                },
            )

        self.assertEqual(
            ["nvidia"],
            [item["provider"] for item in registry["by_id"]["cloud_providers"]["providers"]],
        )
        self.assertTrue(registry["by_id"]["cloud_providers"]["ready"])
        self.assertEqual({"trevor"}, {item["owner_agent"] for item in registry["capabilities"]})

    def test_capability_registry_excludes_retired_airllm_and_keeps_n8n_optional(self):
        from core.capability_registry import build_capability_registry

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            registry = build_capability_registry(root)

        by_id = registry["by_id"]
        self.assertNotIn("airllm", by_id)
        self.assertEqual(registry["policy"]["cloud_control_core"], "nvidia")
        self.assertFalse(by_id["n8n"]["required"])
        self.assertFalse(by_id["n8n"]["degrades_core_chat"])

    def test_traffic_governor_prefers_local_memory_and_keeps_discussion_out_of_openclaw(self):
        from core.traffic_governor import decide_route

        decision = decide_route(
            "你有哪些能力",
            mode="discussion",
            memory_signal={"confidence": "high", "exact_match": True, "source_count": 3},
            capability_registry={
                "by_id": {
                    "openclaw": {"ready": True, "task_forwarding_ready": True},
                    "ollama": {"ready": True},
                }
            },
        )

        self.assertEqual(decision["selected_route"], "local_memory")
        self.assertFalse(decision["openclaw_allowed"])
        self.assertFalse(decision["cloud_allowed"])
        self.assertIn("local_memory_exact_match", decision["reasons"])

    def test_traffic_governor_routes_execution_to_openclaw_before_bridge(self):
        from core.traffic_governor import decide_route

        decision = decide_route(
            "請修復前後端 Debug 問題",
            mode="execution",
            memory_signal={"confidence": "low", "exact_match": False, "source_count": 0},
            capability_registry={
                "by_id": {
                    "openclaw": {"ready": True, "task_forwarding_ready": True},
                    "desktop_bridge": {"ready": True},
                }
            },
        )

        self.assertEqual(decision["task_type"], "execution")
        self.assertTrue(decision["openclaw_allowed"])
        self.assertEqual(decision["route_order"][:2], ["openclaw", "desktop_bridge"])
        self.assertFalse(decision["n8n_required"])

    def test_auto_discussion_prefers_nvidia_control_core(self):
        from desktop_chat_app import DesktopBridge

        bridge = DesktopBridge.__new__(DesktopBridge)
        bridge._load_merged_env_data = lambda: {"CHAT_PREFERRED_PROVIDER": "groq"}

        self.assertEqual(bridge._requested_backend_for_purpose("discussion"), "nvidia")

    def test_auto_discussion_does_not_spend_cloud_when_local_model_is_unhealthy(self):
        from desktop_chat_app import DesktopBridge

        bridge = DesktopBridge.__new__(DesktopBridge)

        self.assertFalse(
            bridge._allow_cloud_fallback_for_requested_backend(
                purpose="discussion",
                model_key="auto",
                interaction_mode="discussion",
            )
        )
        self.assertTrue(
            bridge._allow_cloud_fallback_for_requested_backend(
                purpose="execution",
                model_key="auto",
                interaction_mode="execution",
            )
        )
        self.assertTrue(
            bridge._allow_cloud_fallback_for_requested_backend(
                purpose="discussion",
                model_key="groq",
                interaction_mode="discussion",
            )
        )

    def test_unhealthy_open_source_backend_is_not_attempted_in_auto_discussion(self):
        from desktop_chat_app import DesktopBridge

        bridge = DesktopBridge.__new__(DesktopBridge)
        bridge.oss_is_healthy = False

        self.assertFalse(bridge._should_attempt_live_llm_backend("open_source"))
        self.assertTrue(bridge._should_attempt_live_llm_backend("groq"))

    def test_web_server_exposes_capabilities_and_traffic_policy(self):
        from core.data_paths import ProjectPaths
        from core.web_server import WebServerMode

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            paths = ProjectPaths(root)
            server = WebServerMode(_FakeBridge(root), root, paths)
            readiness = server.readiness_payload()
            topology = server.topology_payload()

        self.assertIn("capability_registry", readiness)
        self.assertIn("capability_registry", topology)
        self.assertIn("traffic_governor", topology)
        self.assertFalse(readiness["capability_registry"]["by_id"]["n8n"]["degrades_core_chat"])
        self.assertTrue(topology["traffic_governor"]["budget_policy"]["local_first"])


if __name__ == "__main__":
    unittest.main()
