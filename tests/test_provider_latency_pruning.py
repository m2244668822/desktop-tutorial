import unittest


class ProviderLatencyPruningTests(unittest.TestCase):
    def test_unconfirmed_or_paid_fallback_providers_fail_closed(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={
                "OPENROUTER_API_KEY": "openrouter-test-value",
                "OPENROUTER_FREE_MODEL": "paid/model",
                "CLOUDFLARE_API_TOKEN": "cloudflare-test-value",
                "CLOUDFLARE_ACCOUNT_ID": "account",
                "CLOUDFLARE_PLAN": "paid",
            },
            free_tier_confirmed={"openrouter", "cloudflare"},
        )

        self.assertFalse(registry.is_available("openrouter"))
        self.assertFalse(registry.is_available("cloudflare"))
        self.assertEqual("paid_model_blocked", registry.state("openrouter").disabled_reason)
        self.assertEqual("free_plan_required", registry.state("cloudflare").disabled_reason)

    def test_quota_failure_opens_circuit_without_paid_fallback(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(env={"NVIDIA_API_KEY": "nvidia-test-value"})
        registry.record_failure("nvidia", status_code=429)
        status = registry.public_status()
        nvidia = next(item for item in status["providers"] if item["provider"] == "nvidia")

        self.assertFalse(registry.is_available("nvidia"))
        self.assertEqual("exhausted", nvidia["quota"]["state"])
        self.assertFalse(nvidia["quota"]["paid_fallback"])
        self.assertTrue(status["free_only"])


if __name__ == "__main__":
    unittest.main()
