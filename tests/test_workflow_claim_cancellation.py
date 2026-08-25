import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class WorkflowClaimCancellationTests(unittest.TestCase):
    def test_claim_loss_stops_step_before_verification_and_followup_writes(self):
        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.workflow_runtime import ToolSpec, _execute_steps

        cancellation = ClaimCancellation()
        calls = []

        def handler(workspace, payload):
            calls.append(('handler', Path(workspace), payload))
            cancellation.mark_lost()
            return {'ok': True}

        def verifier(output):
            calls.append(('verifier', output))
            return True, 'ok'

        registry = {
            'mutating_step': ToolSpec(
                name='mutating_step',
                description='test cancellation boundary',
                handler=handler,
                verifier=verifier,
            )
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                'core.workflow_runtime.build_tool_registry',
                return_value=registry,
            ):
                with self.assertRaises(ClaimLostError):
                    _execute_steps(
                        workspace=Path(tmp),
                        route='test',
                        user_input='cancel',
                        task_id='workflow-cancel',
                        steps=[('mutating_step', {'value': 1})],
                        cancel_check=cancellation.raise_if_lost,
                    )

        self.assertEqual('handler', calls[0][0])
        self.assertEqual(1, len(calls))

    def test_mutating_handler_receives_cancel_check_before_write(self):
        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.workflow_runtime import ToolSpec, _execute_steps

        cancellation = ClaimCancellation()
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'stale-write'

            def handler(workspace, payload, *, cancel_check):
                cancellation.mark_lost()
                cancel_check()
                marker.write_text('stale', encoding='utf-8')
                return {'ok': True}

            registry = {
                'mutating_step': ToolSpec(
                    name='mutating_step',
                    description='test cooperative cancellation',
                    handler=handler,
                    verifier=lambda output: (True, 'ok'),
                )
            }
            with patch(
                'core.workflow_runtime.build_tool_registry',
                return_value=registry,
            ):
                with self.assertRaises(ClaimLostError):
                    _execute_steps(
                        workspace=Path(tmp),
                        route='test',
                        user_input='cancel',
                        task_id='workflow-cooperative-cancel',
                        steps=[('mutating_step', {})],
                        cancel_check=cancellation.raise_if_lost,
                    )

            self.assertFalse(marker.exists())

    def test_aeg_graph_stops_during_history_processing_before_write(self):
        import json

        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.workflow_runtime import _tool_aeg_keyword_graph

        cancellation = ClaimCancellation()
        checks = 0

        def cancel_during_history():
            nonlocal checks
            checks += 1
            if checks == 5:
                cancellation.mark_lost()
            cancellation.raise_if_lost()

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            memory_dir = workspace / 'data' / 'agent_memories'
            memory_dir.mkdir(parents=True)
            (memory_dir / 'conversations.json').write_text(
                json.dumps(
                    {
                        'conversation-1': {
                            'id': 'conversation-1',
                            'messages': [
                                {
                                    'user': '研究自治租約與記憶一致性',
                                    'assistant': '建立安全取消邊界',
                                }
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )

            with self.assertRaises(ClaimLostError):
                _tool_aeg_keyword_graph(
                    workspace,
                    {'limit': 20},
                    cancel_check=cancel_during_history,
                )

            self.assertFalse(
                (workspace / 'data' / 'knowledge_hub' / 'aeg_keyword_graph.json').exists()
            )


if __name__ == '__main__':
    unittest.main()
