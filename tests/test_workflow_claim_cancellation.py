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

    def test_ingestion_generation_rolls_back_all_files_on_cancellation(self):
        import os

        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from tools.build_knowledge_ingestion import _publish_generation

        cancellation = ClaimCancellation()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                root / 'documents.jsonl': b'old documents\n',
                root / 'chunks.jsonl': b'old chunks\n',
                root / 'summary.json': b'{"generation":"old"}\n',
            }
            for path, content in paths.items():
                path.write_bytes(content)
            replacements = {
                path: content.replace(b'old', b'new')
                for path, content in paths.items()
            }
            resolved_replacements = {path.resolve() for path in replacements}
            original_replace = os.replace
            published_targets = 0

            def cancel_after_first_publish(source, destination):
                nonlocal published_targets
                result = original_replace(source, destination)
                if Path(destination).resolve() in resolved_replacements:
                    published_targets += 1
                    if published_targets == 1:
                        cancellation.mark_lost()
                return result

            with patch(
                'tools.build_knowledge_ingestion.os.replace',
                side_effect=cancel_after_first_publish,
            ):
                with self.assertRaises(ClaimLostError):
                    _publish_generation(
                        replacements,
                        cancel_check=cancellation.raise_if_lost,
                    )

            self.assertEqual(paths, {path: path.read_bytes() for path in paths})

    def test_shared_output_rollback_cannot_overwrite_newer_publisher(self):
        import os
        import threading
        import time

        from core.autonomy_claim import ClaimCancellation, ClaimLostError
        from core.workflow_runtime import _write_text_with_cancellation

        cancellation = ClaimCancellation()
        restore_started = threading.Event()
        healthy_finished = threading.Event()
        stale_thread = threading.current_thread()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'shared.json'
            output.write_text('old', encoding='utf-8')
            original_replace = os.replace

            def delayed_replace(source, destination):
                source_path = Path(source)
                if (
                    threading.current_thread() is stale_thread
                    and source_path.name.endswith('.restore')
                ):
                    restore_started.set()
                    time.sleep(0.1)
                result = original_replace(source, destination)
                if (
                    threading.current_thread() is stale_thread
                    and source_path.name.endswith('.tmp')
                ):
                    cancellation.mark_lost()
                return result

            def publish_healthy_output():
                self.assertTrue(restore_started.wait(timeout=2))
                _write_text_with_cancellation(
                    output,
                    'healthy',
                    cancel_check=None,
                )
                healthy_finished.set()

            publisher = threading.Thread(target=publish_healthy_output)
            publisher.start()
            with patch(
                'core.workflow_runtime.os.replace',
                side_effect=delayed_replace,
            ):
                with self.assertRaises(ClaimLostError):
                    _write_text_with_cancellation(
                        output,
                        'stale',
                        cancel_check=cancellation.raise_if_lost,
                    )
            publisher.join(timeout=2)

            self.assertTrue(healthy_finished.is_set())
            self.assertEqual('healthy', output.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
