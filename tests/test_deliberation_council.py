import unittest


def candidate(answer, claim_value, *, confidence=0.9, safe=True, evidence=0.9, requirements=0.9):
    return {
        'answer': answer,
        'claims': [{'key': 'result', 'value': claim_value}],
        'evidence': [{'summary': 'verified source', 'verified': True}],
        'assumptions': [],
        'confidence': confidence,
        'quality': {
            'evidence_verification': evidence,
            'requirement_fit': requirements,
            'safe': safe,
            'privacy_ok': True,
            'format_ok': True,
            'tests_ok': True,
        },
    }


class DeliberationCouncilTests(unittest.TestCase):
    def build_registry(self, extra=None):
        from core.provider_registry import ProviderRegistry

        env = {
            'NVIDIA_API_KEY': 'nvapi-test-value',
            'GEMINI_API_KEY': 'gemini-test-value',
            'GROQ_API_KEY': 'groq-test-value',
            'CEREBRAS_API_KEY': 'cerebras-test-value',
        }
        env.update(extra or {})
        return ProviderRegistry(
            env=env,
            free_tier_confirmed={'gemini', 'groq', 'cerebras', 'openrouter', 'cloudflare'},
        )

    def test_modes_use_expected_provider_sets(self):
        from core.deliberation import DeliberationCouncil

        calls = []

        def runner(provider, request):
            calls.append(provider.name)
            return candidate(provider.name, 'same')

        council = DeliberationCouncil(self.build_registry(), runner=runner)
        fast = council.deliberate('問題', mode='fast')
        self.assertEqual(['nvidia'], fast.metadata['providers'])

        calls.clear()
        cross_check = council.deliberate('問題', mode='cross_check')
        self.assertEqual(2, len(cross_check.metadata['providers']))
        self.assertEqual('nvidia', cross_check.metadata['providers'][0])

        calls.clear()
        rigorous = council.deliberate('問題', mode='rigorous')
        self.assertEqual(
            ['nvidia', 'gemini', 'groq', 'cerebras'],
            rigorous.metadata['providers'],
        )

    def test_coding_mode_uses_laguna_for_nvidia_dialogue(self):
        from core.deliberation import DeliberationCouncil

        models = {}

        def runner(provider, request):
            models[provider.name] = request['model']
            return candidate(provider.name, 'same')

        DeliberationCouncil(self.build_registry(), runner=runner).deliberate(
            '修正程式',
            mode='fast',
            capability_mode='coding',
        )

        self.assertEqual('poolside/laguna-xs-2.1', models['nvidia'])

    def test_candidates_receive_same_sanitized_blind_context_without_tools(self):
        from core.deliberation import DeliberationCouncil

        requests = []

        def runner(provider, request):
            requests.append((provider.name, request))
            return candidate(provider.name, 'same')

        council = DeliberationCouncil(self.build_registry(), runner=runner)
        council.deliberate(
            '我的信箱 owner@example.com，API_KEY=secret-value',
            mode='rigorous',
            memory_context='私密筆記 password=hunter2',
        )

        contexts = [request['trevor_context'] for _, request in requests]
        self.assertTrue(contexts)
        self.assertTrue(all(context == contexts[0] for context in contexts[1:]))
        for _, request in requests:
            self.assertNotIn('tools', request)
            self.assertNotIn('owner@example.com', str(request))
            self.assertNotIn('secret-value', str(request))
            self.assertNotIn('hunter2', str(request))

    def test_hard_gate_rejects_unsafe_high_confidence_candidate(self):
        from core.deliberation import DeliberationCouncil

        def runner(provider, request):
            if provider.name == 'nvidia':
                return candidate('unsafe', 'bad', confidence=1.0, safe=False, evidence=1.0, requirements=1.0)
            return candidate('safe answer', 'good', confidence=0.8, evidence=0.8, requirements=0.9)

        result = DeliberationCouncil(self.build_registry(), runner=runner).deliberate(
            '問題', mode='cross_check'
        )

        self.assertEqual('safe answer', result.answer)
        self.assertIn('nvidia', result.metadata['rejected_providers'])

    def test_major_disagreement_adds_free_arbiter_and_hides_drafts(self):
        from core.deliberation import DeliberationCouncil

        registry = self.build_registry(
            {
                'OPENROUTER_API_KEY': 'or-test-value',
                'OPENROUTER_FREE_MODEL': 'openrouter/free',
            }
        )

        def runner(provider, request):
            if request.get('request_type') == 'arbitration':
                return {'selected_provider': 'nvidia', 'confidence': 0.82}
            value = 'yes' if provider.name in {'nvidia', 'groq'} else 'no'
            return candidate(f'draft from {provider.name}', value, confidence=0.8)

        result = DeliberationCouncil(registry, runner=runner).deliberate('問題', mode='rigorous')
        public = result.public_dict()

        self.assertTrue(result.metadata['arbitrated'])
        self.assertEqual('openrouter', result.metadata['arbiter'])
        self.assertNotIn('candidates', public)
        self.assertNotIn('draft from gemini', str(public))
        self.assertIn('major_disagreement', public['deliberation'])

    def test_429_degrades_without_paid_fallback(self):
        from core.deliberation import DeliberationCouncil
        from core.provider_registry import ProviderCallError

        registry = self.build_registry()

        def runner(provider, request):
            if provider.name == 'gemini':
                raise ProviderCallError('quota', status_code=429)
            return candidate(provider.name, 'same')

        result = DeliberationCouncil(registry, runner=runner).deliberate(
            '問題', mode='rigorous'
        )

        self.assertEqual('degraded', result.metadata['status'])
        self.assertIn('gemini', result.metadata['unavailable_providers'])
        self.assertEqual('quota_exhausted', registry.state('gemini').disabled_reason)
        self.assertNotIn('openai', result.metadata['providers'])

    def test_polish_that_adds_claims_is_rejected(self):
        from core.deliberation import DeliberationCouncil

        def runner(provider, request):
            return candidate('verified base', 'same')

        def polisher(provider, request):
            return {
                'answer': 'polished with invention',
                'claims': [
                    {'key': 'result', 'value': 'same'},
                    {'key': 'invented', 'value': 'new'},
                ],
            }

        result = DeliberationCouncil(
            self.build_registry(),
            runner=runner,
            polisher=polisher,
        ).deliberate('問題', mode='cross_check')

        self.assertEqual('verified base', result.answer)

    def test_shadow_mode_scores_but_keeps_nvidia_answer(self):
        from core.deliberation import DeliberationCouncil

        def runner(provider, request):
            if provider.name == 'nvidia':
                return candidate('nvidia shadow answer', 'same', evidence=0.75, requirements=0.8)
            return candidate('external higher answer', 'same', evidence=1.0, requirements=1.0)

        result = DeliberationCouncil(self.build_registry(), runner=runner).deliberate(
            '問題',
            mode='cross_check',
            shadow=True,
        )

        self.assertEqual('nvidia shadow answer', result.answer)
        self.assertEqual('shadow', result.metadata['status'])
        self.assertNotEqual('nvidia', result.metadata['shadow_recommendation'])


if __name__ == '__main__':
    unittest.main()
