import importlib
import unittest
from pathlib import Path

import agents
from core import agent_prompts


ROOT = Path(__file__).resolve().parents[1]
CHAT_TEMPLATES = (
    ROOT / 'templates' / 'chat.html',
    ROOT / 'templates' / 'chat_shell.html',
    ROOT / 'templates' / 'agent_shell.html',
    ROOT / 'templates' / 'monitor_shell.html',
)


class TrevorIdentityContractTests(unittest.TestCase):
    def test_agent_catalog_exposes_only_trevor(self):
        specs = agents.list_agent_specs()
        self.assertEqual(['trevor'], [spec.key for spec in specs])
        self.assertEqual('崔佛', specs[0].label)

    def test_legacy_agents_normalize_to_trevor_capability_modes(self):
        identity = importlib.import_module('core.trevor_identity')
        expected = {
            'dispatcher': 'general',
            'proclaimer': 'general',
            'engineer': 'coding',
            'researcher': 'research',
            'whitehat': 'security',
            'xiaobian': 'content',
            'learner': 'learning',
        }
        for legacy, mode in expected.items():
            normalized = identity.normalize_trevor_identity(agent=legacy)
            self.assertEqual('trevor', normalized.agent)
            self.assertEqual('崔佛', normalized.role)
            self.assertEqual(mode, normalized.capability_mode)
            self.assertTrue(normalized.deprecated_alias)

    def test_public_response_never_exposes_legacy_identity(self):
        identity = importlib.import_module('core.trevor_identity')
        payload = identity.decorate_trevor_response(
            {'ok': True, 'agent': 'engineer', 'role': '工程師', 'reply': '完成'},
            requested_agent='engineer',
        )
        self.assertEqual('trevor', payload['agent'])
        self.assertEqual('崔佛', payload['role'])
        self.assertEqual('coding', payload['identity']['capability_mode'])
        self.assertEqual(2, payload['identity']['schema_version'])
        self.assertEqual('legacy_agent_alias', payload['deprecations'][0]['code'])

    def test_public_reply_rewrites_legacy_personalities_as_capability_modes(self):
        identity = importlib.import_module('core.trevor_identity')
        reply = identity.canonicalize_trevor_reply(
            '【工程師】研究員提供證據，帽子覆核，最後交給小編。'
            '\n[申言者->工程師交接]',
            'coding',
        )

        self.assertIn('【崔佛｜程式】', reply)
        for legacy in ('工程師', '研究員', '帽子', '小編', '申言者'):
            self.assertNotIn(legacy, reply)
        self.assertIn('崔佛／研究能力', reply)
        self.assertIn('崔佛／安全能力', reply)

    def test_prompt_registry_exposes_only_trevor(self):
        self.assertEqual({'崔佛'}, set(agent_prompts.AGENT_SYSTEM_PROMPTS))
        self.assertEqual(('崔佛',), agent_prompts.AGENT_WINDOW_ROLES)
        self.assertIn('NVIDIA', agent_prompts.get_agent_system_prompt('工程師'))

    def test_frontend_exposes_single_trevor_identity(self):
        for template in CHAT_TEMPLATES:
            html = template.read_text(encoding='utf-8')
            self.assertIn('id="nav-trevor"', html)
            self.assertIn('agentKey: "trevor"', html)
            self.assertIn('label: "崔佛"', html)
            for legacy_nav in (
                'nav-researcher',
                'nav-engineer',
                'nav-xiaobian',
                'nav-proclaimer',
                'nav-whitehat',
                'nav-general',
            ):
                self.assertNotIn(f'id="{legacy_nav}"', html)

    def test_frontend_sends_capability_and_deliberation(self):
        for template in CHAT_TEMPLATES:
            html = template.read_text(encoding='utf-8')
            self.assertIn('id="capabilitySelect"', html)
            self.assertIn('id="deliberationSelect"', html)
            self.assertIn('capability_mode:', html)
            self.assertIn('deliberation:', html)


if __name__ == '__main__':
    unittest.main()
