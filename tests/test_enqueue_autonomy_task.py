import tempfile
import unittest
from pathlib import Path


class EnqueueAutonomyTaskTests(unittest.TestCase):
    def test_legacy_route_becomes_trevor_capability_mode(self):
        from tools.enqueue_autonomy_task import enqueue_task, parse_args

        with tempfile.TemporaryDirectory() as tmp:
            args = parse_args(
                [
                    '--route',
                    '工程師',
                    '--category',
                    'bugfix',
                    '--input',
                    '修正語法',
                ]
            )
            task = enqueue_task(args, Path(tmp))

        self.assertEqual('trevor', task['agent'])
        self.assertEqual('崔佛', task['role'])
        self.assertEqual('coding', task['capability_mode'])
        self.assertEqual('bugfix', task['category'])
        self.assertNotIn('route', task)


if __name__ == '__main__':
    unittest.main()
