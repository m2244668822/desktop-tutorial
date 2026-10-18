import json
import unittest
from unittest.mock import patch

from core.chat_gateway import (
    ChatGatewayBlocked,
    ChatModelGateway,
    ChatRequest,
    CompositeChatTransport,
    RegistryChatTransport,
)
from core.model_router import ModelProvider, ModelRouter, RetryPolicy
from core.provider_registry import ProviderRegistry, ProviderSpec


class FakeChatTransport:
    def __init__(self, failures=None):
        self.failures = set(failures or ())
        self.calls = []

    def generate(self, provider, payload):
        self.calls.append((provider.model_id, payload))
        if provider.model_id in self.failures:
            raise RuntimeError("provider unavailable")
        return f"reply-from-{provider.model_id}"


class FakeRegistry:
    def get(self, provider):
        return ProviderSpec(
            name=provider,
            label="Test provider",
            key_names=("TEST_API_KEY",),
            base_url="https://example.test/v1",
            default_model="test-model",
            model_family="test",
        )


class FakeProviderHttpClient:
    def __init__(self):
        self.calls = []

    def call(self, spec, payload):
        self.calls.append((spec.name, payload))
        return "adapter-reply"


class ChatGatewayTests(unittest.TestCase):
    def test_private_chat_prefers_local_provider_and_keeps_identity(self):
        router = ModelRouter([
            ModelProvider(
                "local-chat", "ollama", {"chat"}, "local", availability="online", priority=1
            ),
            ModelProvider(
                "cloud-chat", "nvidia", {"chat"}, "cloud", availability="online", priority=2
            ),
        ])
        transport = FakeChatTransport()
        gateway = ChatModelGateway(router, transport, retry=RetryPolicy(max_attempts=1))

        result = gateway.complete(
            ChatRequest(
                task_id="task-chat-1",
                run_id="run-chat-1",
                messages=[{"role": "user", "content": "hello"}],
            )
        )

        self.assertEqual("local-chat", result.model_id)
        self.assertEqual("task-chat-1", result.task_id)
        self.assertEqual("run-chat-1", result.run_id)
        self.assertEqual("complete", result.status)
        self.assertEqual(["local-chat"], [model_id for model_id, _ in transport.calls])

    def test_embedding_provider_is_not_eligible_for_chat(self):
        router = ModelRouter([
            ModelProvider(
                "nvidia/nemotron-3-embed-1b",
                "nvidia",
                {"chat"},
                "cloud",
                availability="online",
                capabilities={"embedding"},
            )
        ])
        gateway = ChatModelGateway(router, FakeChatTransport(), retry=RetryPolicy(max_attempts=1))

        with self.assertRaisesRegex(ChatGatewayBlocked, "no_chat_provider"):
            gateway.complete(
                ChatRequest(
                    task_id="task-embed-chat",
                    run_id="run-embed-chat",
                    messages=[{"role": "user", "content": "hello"}],
                    privacy_class="cloud",
                )
            )

    def test_failed_primary_uses_one_eligible_fallback_without_changing_identity(self):
        router = ModelRouter([
            ModelProvider(
                "primary-chat", "nvidia", {"chat"}, "cloud", availability="online", priority=1
            ),
            ModelProvider(
                "fallback-chat", "gemini", {"chat"}, "cloud", availability="online", priority=2
            ),
        ])
        transport = FakeChatTransport(failures={"primary-chat"})
        gateway = ChatModelGateway(router, transport, retry=RetryPolicy(max_attempts=1))

        result = gateway.complete(
            ChatRequest(
                task_id="task-fallback-1",
                run_id="run-fallback-1",
                messages=[{"role": "user", "content": "public question"}],
                privacy_class="cloud",
            )
        )

        self.assertEqual("fallback-chat", result.model_id)
        self.assertTrue(result.fallback_used)
        self.assertEqual(("primary-chat", "fallback-chat"), result.attempted_models)
        self.assertEqual("task-fallback-1", result.task_id)
        self.assertEqual("run-fallback-1", result.run_id)

    def test_exhausted_providers_are_blocked_without_fake_reply(self):
        router = ModelRouter([
            ModelProvider(
                "only-chat", "ollama", {"chat"}, "local", availability="online", priority=1
            )
        ])
        gateway = ChatModelGateway(
            router,
            FakeChatTransport(failures={"only-chat"}),
            retry=RetryPolicy(max_attempts=1),
        )

        with self.assertRaisesRegex(ChatGatewayBlocked, "chat_providers_exhausted"):
            gateway.complete(
                ChatRequest(
                    task_id="task-blocked-1",
                    run_id="run-blocked-1",
                    messages=[{"role": "user", "content": "hello"}],
                )
            )

    def test_registry_transport_forwards_chat_payload_without_credentials(self):
        registry = FakeRegistry()
        client = FakeProviderHttpClient()
        transport = RegistryChatTransport(registry, client)
        router = ModelRouter([
            ModelProvider(
                "nvidia/test-chat",
                "nvidia",
                {"chat"},
                "cloud",
                availability="online",
                priority=1,
            )
        ])
        gateway = ChatModelGateway(router, transport, retry=RetryPolicy(max_attempts=1))

        result = gateway.complete(
            ChatRequest(
                task_id="task-adapter-1",
                run_id="run-adapter-1",
                messages=[{"role": "user", "content": "hello"}],
                privacy_class="cloud",
            )
        )

        self.assertEqual("adapter-reply", result.content)
        self.assertEqual("nvidia", client.calls[0][0])
        self.assertEqual("nvidia/test-chat", client.calls[0][1]["model"])
        self.assertNotIn("TEST_API_KEY", client.calls[0][1])

    def test_registry_transport_preserves_response_reasoning_details(self):
        registry = FakeRegistry()

        class MetadataClient:
            def call_with_metadata(self, spec, payload):
                return {
                    "content": "answer",
                    "reasoning_details": [
                        {"type": "reasoning.summary", "data": "opaque"},
                    ],
                    "tool_calls": [],
                }

        provider = ModelProvider(
            "nvidia/test-chat",
            "nvidia",
            {"chat"},
            "cloud",
            availability="online",
            priority=1,
        )
        transport = RegistryChatTransport(registry, MetadataClient())
        result = transport.generate_response(provider, {"messages": []})

        self.assertEqual("answer", result["content"])
        self.assertEqual(
            [{"type": "reasoning.summary", "data": "opaque"}],
            result["reasoning_details"],
        )

    def test_gateway_response_keeps_reasoning_details_for_follow_up(self):
        class MetadataTransport(FakeChatTransport):
            def generate_response(self, provider, payload):
                return {
                    "content": "answer",
                    "reasoning_details": [{"type": "reasoning.summary", "data": "opaque"}],
                    "tool_calls": [{"id": "call-1"}],
                }

        router = ModelRouter([
            ModelProvider(
                "openrouter/nemotron-ultra:free",
                "openrouter",
                {"chat"},
                "cloud",
                availability="online",
                priority=1,
            )
        ])
        result = ChatModelGateway(
            router,
            MetadataTransport(),
            retry=RetryPolicy(max_attempts=1),
        ).complete(
            ChatRequest(
                task_id="task-reasoning-response",
                run_id="run-reasoning-response",
                messages=[{"role": "user", "content": "hello"}],
                privacy_class="cloud",
            )
        )

        self.assertEqual(
            [{"type": "reasoning.summary", "data": "opaque"}],
            result.reasoning_details,
        )

        continuation = result.as_assistant_message()
        self.assertIs(
            result.reasoning_details,
            continuation["reasoning_details"],
        )
        self.assertEqual("assistant", continuation["role"])
        self.assertNotIn("execute", continuation)
        self.assertEqual([{"id": "call-1"}], result.tool_calls)

    def test_continue_chat_preserves_reasoning_on_same_model_only(self):
        class MetadataTransport(FakeChatTransport):
            def generate_response(self, provider, payload):
                self.calls.append((provider.model_id, payload))
                return {
                    "content": "answer-" + str(len(self.calls)),
                    "reasoning_details": [{"type": "reasoning.summary", "data": "opaque"}],
                }

        model = "nvidia/nemotron-3-ultra-550b-a55b:free"
        router = ModelRouter([
            ModelProvider(model, "openrouter", {"chat"}, "cloud", availability="online", priority=1),
            ModelProvider("fallback-chat", "gemini", {"chat"}, "cloud", availability="online", priority=2),
        ])
        transport = MetadataTransport()
        gateway = ChatModelGateway(router, transport, retry=RetryPolicy(max_attempts=1))
        request = ChatRequest(
            task_id="task-continuation",
            run_id="run-continuation",
            messages=[{"role": "user", "content": "How many r's are in strawberry?"}],
            privacy_class="cloud",
            preferred_model=model,
            extra_body={"reasoning": {"enabled": True}},
        )

        first = gateway.complete(request)
        second = gateway.continue_chat(request, first, "Are you sure? Think carefully.")

        self.assertEqual(model, second.model_id)
        self.assertEqual(2, len(transport.calls))
        follow_up = transport.calls[1][1]["messages"]
        self.assertEqual("assistant", follow_up[1]["role"])
        self.assertIs(first.reasoning_details, follow_up[1]["reasoning_details"])
        self.assertEqual("Are you sure? Think carefully.", follow_up[2]["content"])
        self.assertEqual({"enabled": True}, transport.calls[1][1]["reasoning"])

    def test_continue_chat_does_not_fallback_when_original_model_is_unavailable(self):
        model = "nvidia/nemotron-3-ultra-550b-a55b:free"
        router = ModelRouter([
            ModelProvider(model, "openrouter", {"chat"}, "cloud", availability="online", priority=1),
            ModelProvider("fallback-chat", "gemini", {"chat"}, "cloud", availability="online", priority=2),
        ])
        transport = FakeChatTransport()
        gateway = ChatModelGateway(router, transport, retry=RetryPolicy(max_attempts=1))
        request = ChatRequest(
            task_id="task-no-fallback",
            run_id="run-no-fallback",
            messages=[{"role": "user", "content": "hello"}],
            privacy_class="cloud",
            preferred_model=model,
        )
        first = gateway.complete(request)
        router.providers[model].availability = "unavailable"

        with self.assertRaisesRegex(ChatGatewayBlocked, "no_chat_provider"):
            gateway.continue_chat(request, first, "follow up")
        self.assertEqual([model], [model_id for model_id, _ in transport.calls])

    def test_ollama_transport_maps_chat_payload_and_extracts_reply(self):
        from core.chat_gateway import OllamaChatTransport

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"message": {"content": "local answer"}}).encode()

        provider = ModelProvider(
            "qwen2.5:1.5b",
            "ollama",
            {"chat"},
            "local",
            availability="online",
        )
        transport = OllamaChatTransport(endpoint="http://127.0.0.1:11434/api/chat")
        with patch("core.chat_gateway.urllib_request.urlopen", return_value=Response()) as open_url:
            reply = transport.generate(
                provider,
                {"messages": [{"role": "user", "content": "hi"}], "temperature": 0.2},
            )

        self.assertEqual("local answer", reply)
        sent = json.loads(open_url.call_args.args[0].data.decode())
        self.assertEqual("qwen2.5:1.5b", sent["model"])
        self.assertFalse(sent["stream"])
        self.assertEqual(0.2, sent["options"]["temperature"])

    def test_composite_transport_routes_local_and_registry_separately(self):
        class Local:
            def generate(self, provider, payload):
                return "local"

        class Cloud:
            def generate(self, provider, payload):
                return "cloud"

        transport = CompositeChatTransport(local=Local(), registry=Cloud())
        self.assertEqual(
            "local",
            transport.generate(
                ModelProvider("qwen", "ollama", {"chat"}, "local", availability="online"),
                {},
            ),
        )
        self.assertEqual(
            "cloud",
            transport.generate(
                ModelProvider("cloud", "openrouter", {"chat"}, "cloud", availability="online"),
                {},
            ),
        )

    def test_runtime_registry_keeps_nemotron_embedding_out_of_chat_route(self):
        registry = ProviderRegistry(
            env={
                "NVIDIA_API_KEY": "nvapi-test-value",
                "NVIDIA_CONTROL_MODEL": "nvidia/nemotron-3-embed-1b",
            }
        )
        router = ModelRouter.from_runtime_registry(registry)
        gateway = ChatModelGateway(router, FakeChatTransport(), retry=RetryPolicy(max_attempts=1))

        with self.assertRaisesRegex(ChatGatewayBlocked, "no_chat_provider"):
            gateway.complete(
                ChatRequest(
                    task_id="task-registry-embed",
                    run_id="run-registry-embed",
                    messages=[{"role": "user", "content": "hello"}],
                    privacy_class="cloud",
                )
            )

    def test_runtime_registry_marks_local_model_as_chat_capable(self):
        registry = ProviderRegistry(env={})
        router = ModelRouter.from_runtime_registry(registry, local_model="qwen-local")

        local = router.providers["qwen-local"]
        self.assertIn("chat", local.roles)
        self.assertIn("chat", local.capabilities)

    def test_chat_request_forwards_reasoning_controls(self):
        router = ModelRouter([
            ModelProvider(
                "openrouter/nemotron-ultra:free",
                "openrouter",
                {"chat"},
                "cloud",
                availability="online",
                priority=1,
            )
        ])
        transport = FakeChatTransport()
        gateway = ChatModelGateway(router, transport, retry=RetryPolicy(max_attempts=1))

        gateway.complete(
            ChatRequest(
                task_id="task-reasoning-1",
                run_id="run-reasoning-1",
                messages=[{"role": "user", "content": "count the letters"}],
                privacy_class="cloud",
                extra_body={"reasoning": {"enabled": True}},
            )
        )

        self.assertEqual(
            {"enabled": True},
            transport.calls[0][1]["reasoning"],
        )

    def test_provider_output_cap_limits_requested_tokens(self):
        router = ModelRouter([
            ModelProvider(
                "bounded-chat",
                "openrouter",
                {"chat"},
                "cloud",
                availability="online",
                max_output_tokens=64,
            )
        ])
        transport = FakeChatTransport()
        ChatModelGateway(router, transport, retry=RetryPolicy(max_attempts=1)).complete(
            ChatRequest(
                task_id="task-token-cap",
                run_id="run-token-cap",
                messages=[{"role": "user", "content": "hello"}],
                privacy_class="cloud",
                max_tokens=4096,
            )
        )
        self.assertEqual(64, transport.calls[0][1]["max_tokens"])


if __name__ == "__main__":
    unittest.main()
