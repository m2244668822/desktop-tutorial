import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TaskBoardTrevorIdentityTests(unittest.TestCase):
    def test_task_board_reads_only_the_canonical_trevor_data_root(self):
        from core.task_board import task_items_payload, task_summary_payload

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / 'workspace'
            data_root = root / 'trevor-data'
            legacy_queue = workspace / 'data' / 'autonomy' / 'task_queue.json'
            canonical_queue = data_root / 'autonomy' / 'task_queue.json'
            legacy_queue.parent.mkdir(parents=True)
            canonical_queue.parent.mkdir(parents=True)
            legacy_queue.write_text(
                json.dumps({'tasks': [{'id': 'legacy', 'status': 'pending'}]}),
                encoding='utf-8',
            )
            canonical_queue.write_text(
                json.dumps({'tasks': [{'id': 'canonical', 'status': 'failed'}]}),
                encoding='utf-8',
            )

            with patch.dict(os.environ, {'TREVOR_DATA_DIR': str(data_root)}):
                payload = task_items_payload(workspace)
                summary = task_summary_payload(workspace)

        self.assertEqual(['canonical'], [item['id'] for item in payload['items']])
        self.assertEqual(0, summary['unresolved_count'])
        self.assertEqual([str(canonical_queue.resolve())], summary['sources'])

    def test_legacy_route_is_exposed_only_as_capability_mode(self):
        from core.task_board import task_items_payload

        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / 'data' / 'autonomy' / 'task_queue.json'
            queue.parent.mkdir(parents=True)
            queue.write_text(
                json.dumps(
                    {
                        'tasks': [
                            {
                                'id': 'task-1',
                                'route': '工程師',
                                'input': '修正測試',
                                'status': 'pending',
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding='utf-8',
            )

            item = task_items_payload(tmp)['items'][0]

        self.assertEqual('trevor', item['assigned_agent'])
        self.assertEqual('崔佛', item['agent_label'])
        self.assertEqual('coding', item['capability_mode'])
        self.assertEqual('trevor', item['route'])


if __name__ == '__main__':
    unittest.main()
