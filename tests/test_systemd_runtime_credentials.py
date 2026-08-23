import base64
import tempfile
import unittest
from pathlib import Path


class _EmptyStore:
    def get_secret(self, service, account):
        from core.keychain_credentials import CredentialResult

        return CredentialResult(False, 'keychain', error_code='credential_missing')


class SystemdRuntimeCredentialTests(unittest.TestCase):
    def test_device_encryption_key_prefers_systemd_credential(self):
        from core.encrypted_store import DeviceEncryptionKey

        with tempfile.TemporaryDirectory() as tmp:
            key = bytes(range(32))
            credential = Path(tmp) / 'trevor_memory_key_b64'
            credential.write_text(base64.b64encode(key).decode('ascii'), encoding='utf-8')

            loaded = DeviceEncryptionKey(
                credential_store=_EmptyStore(), credentials_directory=tmp
            ).get_or_create()

        self.assertEqual(key, loaded)

    def test_ai_horde_uses_systemd_credential_without_keychain(self):
        from core.ai_horde_client import AIHordeClient

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'ai_horde_api_key').write_text('systemd-horde-key', encoding='utf-8')
            client = AIHordeClient(
                credential_store=_EmptyStore(), credentials_directory=tmp
            )

            status = client.public_status()

        self.assertTrue(status['configured'])
        self.assertEqual('systemd', status['key_source'])
        self.assertNotIn('systemd-horde-key', repr(client))


if __name__ == '__main__':
    unittest.main()
