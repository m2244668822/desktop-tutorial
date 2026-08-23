import json
import tempfile
import unittest
from pathlib import Path


class TaskBoardTrevorIdentityTests(unittest.TestCase):
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
