import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_frontend_backend_launcher_has_no_machine_specific_path(self):
        source = (ROOT / 'start_frontend_backend.py').read_text(encoding='utf-8')

        self.assertNotIn(r'g:\城城城程式', source)
        self.assertIn('Path(__file__).resolve().parent', source)

    def test_system_main_uses_trevor_autonomy_defaults(self):
        import system_main

        args = system_main.parse_args(['autopilot'])

        self.assertEqual(60, args.autopilot_heartbeat)
        self.assertEqual(900, args.autopilot_evaluation)


if __name__ == '__main__':
    unittest.main()
