import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ProviderRegistryTests(unittest.TestCase):
    def test_nvidia_never_uses_openai_key_fallback(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(env={'OPENAI_API_KEY': 'sk-not-for-nvidia'})
        nvidia = registry.get('nvidia')

        self.assertEqual(('NVIDIA_API_KEY', 'NVAPI_API_KEY'), nvidia.key_names)
        self.assertFalse(registry.is_available('nvidia'))

    def test_legacy_runtime_resolver_also_rejects_openai_fallback(self):
        from core.llm_cns import resolve_provider_config

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {'OPENAI_API_KEY': 'sk-not-for-nvidia'},
            clear=True,
        ):
            resolved = resolve_provider_config(Path(tmp), 'nvidia')

        self.assertEqual('', resolved['key'])
        self.assertEqual('NVIDIA_API_KEY', resolved['key_name'])

    def test_default_models_and_authority_match_trevor_contract(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(env={'NVIDIA_API_KEY': 'nvapi-test-value'})

        self.assertEqual(
            'nvidia/nemotron-3-ultra-550b-a55b',
            registry.model_for('nvidia', 'control'),
        )
        self.assertEqual('poolside/laguna-xs-2.1', registry.model_for('nvidia', 'coding'))
        self.assertEqual(
            'z-ai/glm-5.2',
            registry.model_for('nvidia', 'general_backup'),
        )
        self.assertTrue(registry.get('nvidia').control_authority)
        self.assertFalse(registry.get('gemini').control_authority)

    def test_provider_prompts_keep_trevor_authority_separate_from_candidate_seats(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={
                'NVIDIA_API_KEY': 'nvapi-test-value',
                'GEMINI_API_KEY': 'gemini-test-value',
            },
            free_tier_confirmed={'gemini'},
        )
        context = {
            'runtime_capabilities': {
                'workspace_files': {'ready': True},
                'persistent_memory': {'ready': True},
            }
        }

        nvidia_request = registry.build_dialogue_request('nvidia', context)
        gemini_request = registry.build_dialogue_request('gemini', context)
        nvidia_prompt = nvidia_request['messages'][0]['content']
        gemini_prompt = gemini_request['messages'][0]['content']

        self.assertIn('NVIDIA control core', nvidia_prompt)
        self.assertIn('Trevor runtime', nvidia_prompt)
        self.assertNotIn('You have no tools, task API, autonomy API', nvidia_prompt)
        self.assertIn('read-only external candidate', gemini_prompt)
        self.assertIn('Do not generalize this seat limitation to Trevor', gemini_prompt)

    def test_openrouter_and_cloudflare_fail_closed_on_cost(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={
                'OPENROUTER_API_KEY': 'or-test-value',
                'OPENROUTER_FREE_MODEL': 'paid/model',
                'CLOUDFLARE_API_TOKEN': 'cf-test-value',
                'CLOUDFLARE_ACCOUNT_ID': 'account-id',
                'CLOUDFLARE_PLAN': 'paid',
            },
            free_tier_confirmed={'openrouter', 'cloudflare'},
        )

        self.assertFalse(registry.is_available('openrouter'))
        self.assertFalse(registry.is_available('cloudflare'))
        self.assertEqual('paid_model_blocked', registry.state('openrouter').disabled_reason)
        self.assertEqual('free_plan_required', registry.state('cloudflare').disabled_reason)

    def test_public_status_never_contains_credentials(self):
        from core.provider_registry import ProviderRegistry

        secrets = {
            'NVIDIA_API_KEY': 'nvapi-private-value',
            'GEMINI_API_KEY': 'gemini-private-value',
        }
        registry = ProviderRegistry(env=secrets, free_tier_confirmed={'gemini'})
        rendered = json.dumps(registry.public_status(), ensure_ascii=False)

        for value in secrets.values():
            self.assertNotIn(value, rendered)
        self.assertNotIn('credential', rendered.lower())

    def test_model_discovery_disables_missing_model(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={'GEMINI_API_KEY': 'gemini-test-value'},
            free_tier_confirmed={'gemini'},
        )
        registry.validate_models(lambda provider: {'gemini-other'} if provider == 'gemini' else set())

        self.assertFalse(registry.is_available('gemini'))
        self.assertEqual('model_unavailable', registry.state('gemini').disabled_reason)

    def test_model_discovery_disables_invalid_provider_credential(self):
        from core.provider_registry import ProviderCallError, ProviderRegistry

        registry = ProviderRegistry(
            env={'GEMINI_API_KEY': 'gemini-test-value'},
            free_tier_confirmed={'gemini'},
        )

        def invalid_credential(_provider):
            raise ProviderCallError('redacted', status_code=400)

        registry.validate_models(invalid_credential)

        self.assertFalse(registry.is_available('gemini'))
        self.assertEqual(
            'authentication_failed',
            registry.state('gemini').disabled_reason,
        )

    def test_model_discovery_prunes_missing_nvidia_fallback_only(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={
                'NVIDIA_API_KEY': 'nvapi-test-value',
                'NVIDIA_GENERAL_BACKUP_MODEL': 'missing/model',
            }
        )
        registry.validate_models(
            lambda provider: {
                'nvidia/nemotron-3-ultra-550b-a55b',
                'poolside/laguna-xs-2.1',
            }
            if provider == 'nvidia'
            else set()
        )

        self.assertTrue(registry.is_available('nvidia'))
        self.assertEqual((), registry.fallback_models_for('nvidia'))

    def test_duplicate_model_family_disables_fake_diversity_seat(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={
                'GROQ_API_KEY': 'groq-test-value',
                'CEREBRAS_API_KEY': 'cerebras-test-value',
                'CEREBRAS_MODEL': 'openai/gpt-oss-120b',
            },
            free_tier_confirmed={'groq', 'cerebras'},
        )

        self.assertTrue(registry.is_available('groq'))
        self.assertFalse(registry.is_available('cerebras'))
        self.assertEqual('duplicate_model_family', registry.state('cerebras').disabled_reason)

    def test_openrouter_request_enforces_free_private_routing(self):
        from core.provider_registry import ProviderRegistry

        registry = ProviderRegistry(
            env={
                'OPENROUTER_API_KEY': 'or-test-value',
                'OPENROUTER_FREE_MODEL': 'openrouter/free',
            },
            free_tier_confirmed={'openrouter'},
        )
        request = registry.build_dialogue_request(
            'openrouter',
            {'messages': [{'role': 'user', 'content': 'safe'}]},
        )

        self.assertTrue(request['provider']['zdr'])
        self.assertEqual('deny', request['provider']['data_collection'])
        self.assertFalse(request['provider']['allow_fallbacks'])
        self.assertEqual({'prompt': 0, 'completion': 0}, request['provider']['max_price'])
        self.assertNotIn('tools', request)


if __name__ == '__main__':
    unittest.main()
