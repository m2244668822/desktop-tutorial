import os
import stat
import tempfile
import unittest
from pathlib import Path


class CredentialStagingTests(unittest.TestCase):
    def test_credentials_are_private_and_removed_after_context(self):
        from core.credential_staging import staged_credentials

        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            with staged_credentials(
                {'gemini_api_key': 'private-value'}, parent=parent
            ) as directory:
                credential = directory / 'gemini_api_key'
                self.assertEqual('private-value', credential.read_text(encoding='utf-8'))
                self.assertEqual(
                    stat.S_IRUSR,
                    stat.S_IMODE(credential.stat().st_mode),
                )
                self.assertEqual(
                    stat.S_IRWXU,
                    stat.S_IMODE(directory.stat().st_mode),
                )
            self.assertFalse(directory.exists())
            self.assertFalse(any(parent.iterdir()))

    def test_invalid_credential_name_is_rejected(self):
        from core.credential_staging import staged_credentials

        with self.assertRaises(ValueError), staged_credentials({'../secret': 'value'}):
            pass


if __name__ == '__main__':
    unittest.main()
