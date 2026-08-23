import tempfile
import unittest
from pathlib import Path


class TrevorAPIKeyTests(unittest.TestCase):
    def test_create_stores_only_hmac_and_verifies_scopes(self):
        from core.user_api_keys import TrevorAPIKeyStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'keys.json'
            store = TrevorAPIKeyStore(path, hmac_secret=b'x' * 32)
            created = store.create('edge-device', {'chat', 'memory'})
            api_key = created['api_key']
            raw = path.read_text(encoding='utf-8')

            allowed = store.authenticate(api_key, required_scope='chat')
            denied = store.authenticate(api_key, required_scope='git')

        self.assertTrue(api_key.startswith('trv_'))
        self.assertNotIn(api_key, raw)
        self.assertTrue(allowed['ok'])
        self.assertEqual('scope_denied', denied['error'])
        self.assertNotIn('digest', created['record'])

    def test_revoked_and_unknown_keys_fail_closed(self):
        from core.user_api_keys import TrevorAPIKeyStore

        with tempfile.TemporaryDirectory() as tmp:
            store = TrevorAPIKeyStore(Path(tmp) / 'keys.json', hmac_secret=b'y' * 32)
            created = store.create('admin', {'users', 'audit'})
            store.revoke(created['record']['id'])

            revoked = store.authenticate(created['api_key'], required_scope='audit')
            unknown = store.authenticate('trv_unknown', required_scope='audit')

        self.assertEqual('key_revoked', revoked['error'])
        self.assertEqual('invalid_key', unknown['error'])

    def test_invalid_scope_is_rejected(self):
        from core.user_api_keys import TrevorAPIKeyStore

        with tempfile.TemporaryDirectory() as tmp:
            store = TrevorAPIKeyStore(Path(tmp) / 'keys.json', hmac_secret=b'z' * 32)
            with self.assertRaisesRegex(ValueError, 'invalid_scope'):
                store.create('invalid', {'payments'})


if __name__ == '__main__':
    unittest.main()
