import unittest
import tempfile
import base64
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

    def test_linux_web_start_requires_an_explicit_memory_key(self):
        import system_main

        with self.assertRaisesRegex(RuntimeError, 'linux_memory_key_required'):
            system_main.validate_linux_memory_key({}, platform_name='Linux')

        with tempfile.TemporaryDirectory() as tmp:
            credentials = Path(tmp)
            (credentials / 'trevor_memory_key_b64').write_text(
                base64.b64encode(b'k' * 32).decode('ascii'), encoding='utf-8'
            )

            system_main.validate_linux_memory_key(
                {'CREDENTIALS_DIRECTORY': str(credentials)},
                platform_name='Linux',
            )

        system_main.validate_linux_memory_key({}, platform_name='Darwin')


if __name__ == '__main__':
    unittest.main()
