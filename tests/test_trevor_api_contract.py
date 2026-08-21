import unittest
import json
from pathlib import Path

from desktop_chat_app import DesktopBridge


ROOT = Path(__file__).resolve().parents[1]
WEB_SERVER = ROOT / 'core' / 'web_server.py'


class TrevorApiContractTests(unittest.TestCase):
    def setUp(self):
        self.bridge = DesktopBridge(energy_lite=True)
        self.bridge.enable_live_llm_default = False
        self.bridge.memory_manager = None
        self.bridge._run_keyword_retrieval = lambda *_args, **_kwargs: {
            'match_count': 0,
            'items': [],
        }
        self.bridge._build_retrieval_brief = lambda *_args, **_kwargs: ''
        self.bridge._remember_dialog_turn = lambda **_kwargs: None
        self.bridge._record_turn_artifacts = lambda **_kwargs: None
        self.bridge._persist_training_overlay_sample = lambda **_kwargs: None

    def tearDown(self):
        self.bridge.stop_background_monitor()

    def test_send_message_canonicalizes_legacy_role(self):
        result = self.bridge.send_message(
            '你好',
            role='工程師',
            model_key='nvidia',
            interaction_mode='discussion',
        )
        self.assertEqual('trevor', result['agent'])
        self.assertEqual('崔佛', result['role'])
        self.assertEqual('coding', result['identity']['capability_mode'])
        self.assertEqual('legacy_agent_alias', result['deprecations'][0]['code'])
        self.assertNotIn('【工程師】', result['reply'])

    def test_memory_status_has_one_public_identity(self):
        status = self.bridge.get_agent_memory_aeg_status()
        self.assertEqual('single_identity_capability_modes', status['capability_model'])
        self.assertEqual(['崔佛'], [item['role'] for item in status['roles']])

    def test_trevor_status_and_provider_routes_exist(self):
        source = WEB_SERVER.read_text(encoding='utf-8')
        self.assertIn('"/api/trevor/status"', source)
        self.assertIn('"/api/trevor/providers"', source)
        self.assertIn('server_instance.trevor_status_payload()', source)
        self.assertIn('server_instance.trevor_provider_payload()', source)

    def test_bridge_provider_status_is_sanitized_registry_output(self):
        rendered = json.dumps(self.bridge.get_trevor_provider_status(), ensure_ascii=False)
        self.assertNotIn('api_key', rendered.lower())
        self.assertNotIn('authorization', rendered.lower())
        self.assertIn('nvidia', rendered.lower())

    def test_send_message_uses_deliberation_result(self):
        captured = {}

        def fake_live_reply(**kwargs):
            captured.update(kwargs)
            return '委員會答案', {
                'ok': True,
                'attempted': True,
                'provider': 'nvidia',
                'deliberation': {
                    'mode': 'rigorous',
                    'status': 'complete',
                    'providers': ['nvidia', 'gemini', 'groq', 'cerebras'],
                    'agreement_score': 0.84,
                    'confidence': 0.91,
                },
            }

        self.bridge.enable_live_llm_default = True
        self.bridge._generate_live_llm_reply = fake_live_reply
        self.bridge._should_attempt_live_llm_backend = lambda _backend: True
        result = self.bridge.send_message(
            '比較這個方案',
            role='崔佛',
            model_key='nvidia',
            interaction_mode='discussion',
            capability_mode='research',
            deliberation='rigorous',
        )

        self.assertEqual('委員會答案', result['reply'])
        self.assertEqual('research', captured['capability_mode'])
        self.assertEqual('rigorous', captured['deliberation'])
        self.assertEqual('complete', result['deliberation']['status'])

    def test_send_route_accepts_new_contract_fields(self):
        source = WEB_SERVER.read_text(encoding='utf-8')
        self.assertIn('payload.get("capability_mode", "")', source)
        self.assertIn('payload.get("deliberation", "auto")', source)


if __name__ == '__main__':
    unittest.main()
