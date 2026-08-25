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


if __name__ == '__main__':
    unittest.main()
