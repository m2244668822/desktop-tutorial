import tempfile
import unittest
from pathlib import Path


class SecretScannerTests(unittest.TestCase):
    def test_detects_secret_without_returning_its_value(self):
        from core.secret_scanner import SecretScanner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = 'nvapi-' + ('A' * 40)
            (root / 'unsafe.env').write_text(
                f'NVIDIA_API_KEY={secret}\n', encoding='utf-8'
            )

            result = SecretScanner(root).scan_paths([root / 'unsafe.env'])

            self.assertFalse(result['ok'])
            self.assertEqual('nvidia_api_key', result['findings'][0]['rule'])
            self.assertNotIn(secret, str(result))

    def test_allows_empty_and_placeholder_example_values(self):
        from core.secret_scanner import SecretScanner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / '.env.example'
            example.write_text(
                'NVIDIA_API_KEY=\nGROQ_API_KEY=your_groq_api_key_here\n',
                encoding='utf-8',
            )

            result = SecretScanner(root).scan_paths([example])

            self.assertTrue(result['ok'])
            self.assertEqual([], result['findings'])

    def test_detects_private_key_material(self):
        from core.secret_scanner import SecretScanner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = root / 'id_ed25519'
            header = '-----BEGIN ' + 'OPENSSH PRIVATE KEY-----'
            key.write_text(
                f'{header}\nnot-a-real-key\n',
                encoding='utf-8',
            )

            result = SecretScanner(root).scan_paths([key])

            self.assertFalse(result['ok'])
            self.assertEqual('private_key', result['findings'][0]['rule'])

    def test_scans_files_when_parent_directory_is_named_tmp(self):
        from core.secret_scanner import SecretScanner

        with tempfile.TemporaryDirectory() as outer:
            root = Path(outer) / 'tmp' / 'repository'
            root.mkdir(parents=True)
            secret_file = root / 'unsafe.env'
            secret_file.write_text(
                'GROQ_API_KEY=gsk_' + ('B' * 40) + '\n',
                encoding='utf-8',
            )

            result = SecretScanner(root).scan_paths([secret_file])

        self.assertFalse(result['ok'])
        self.assertEqual('groq_api_key', result['findings'][0]['rule'])


if __name__ == '__main__':
    unittest.main()
