import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class _CredentialResult:
    configured = True


class _CredentialStore:
    def __init__(self):
        self.saved = {}

    def set_secret(self, service, account, value):
        self.saved[(service, account)] = value
        return _CredentialResult()


class RemoteAPIKeyBootstrapTests(unittest.TestCase):
    def test_server_issues_key_in_remote_store_without_persisting_plaintext(self):
        from tools.issue_trevor_api_key import issue_api_key

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            credentials = root / 'credentials'
            credentials.mkdir()
            (credentials / 'trevor_api_hmac').write_text('h' * 32, encoding='utf-8')

            issued = issue_api_key(
                root / 'data',
                credentials,
                label='mac-edge',
                scopes={'chat', 'memory', 'tasks'},
            )
            raw = (root / 'data' / 'auth' / 'api_keys.json').read_text(
                encoding='utf-8'
            )

        self.assertTrue(issued['api_key'].startswith('trv_'))
        self.assertNotIn(issued['api_key'], raw)
        self.assertEqual(
            ['chat', 'memory', 'tasks'], issued['record']['scopes']
        )

    def test_server_drops_to_service_owner_before_writing_key_store(self):
        from tools.issue_trevor_api_key import issue_api_key

        privilege_drops = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            credentials = root / 'credentials'
            credentials.mkdir()
            (credentials / 'trevor_api_hmac').write_text('h' * 32, encoding='utf-8')

            def drop_privileges(user, data_root):
                self.assertFalse((data_root / 'auth' / 'api_keys.json').exists())
                privilege_drops.append((user, data_root))

            issue_api_key(
                root / 'data',
                credentials,
                label='mac-edge',
                scopes={'chat'},
                service_user='trevor',
                privilege_dropper=drop_privileges,
            )

        self.assertEqual(
            [('trevor', (root / 'data').resolve())],
            privilege_drops,
        )

    def test_privilege_dropper_never_chowns_service_controlled_paths_as_root(self):
        from tools import issue_trevor_api_key as issuer

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'data'
            root.mkdir()
            account = SimpleNamespace(pw_uid=987, pw_gid=654)

            with (
                patch.object(issuer.pwd, 'getpwnam', return_value=account),
                patch.object(issuer.os, 'geteuid', side_effect=[0, account.pw_uid]),
                patch.object(issuer.os, 'chown') as chown,
                patch.object(issuer.os, 'initgroups') as initgroups,
                patch.object(issuer.os, 'setgid') as setgid,
                patch.object(issuer.os, 'setuid') as setuid,
            ):
                issuer.drop_to_service_user('trevor', root)

        chown.assert_not_called()
        initgroups.assert_called_once_with('trevor', account.pw_gid)
        setgid.assert_called_once_with(account.pw_gid)
        setuid.assert_called_once_with(account.pw_uid)

    def test_mac_bootstrap_saves_only_remote_issued_key_to_keychain(self):
        from tools.bootstrap_trevor_api_key import bootstrap_remote_admin

        remote_key = 'trv_' + 'A' * 43
        store = _CredentialStore()
        commands = []

        def runner(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        'ok': True,
                        'api_key': remote_key,
                        'record': {
                            'id': 'key-id',
                            'prefix': remote_key[:12],
                            'scopes': ['chat', 'memory', 'tasks'],
                        },
                    }
                ),
                stderr='',
            )

        with tempfile.TemporaryDirectory() as tmp:
            ssh_key = Path(tmp) / 'trevor_ed25519'
            ssh_key.write_text('test-key-placeholder', encoding='utf-8')
            result = bootstrap_remote_admin(
                'opc@trevor.example.ts.net',
                ssh_key=ssh_key,
                credential_store=store,
                runner=runner,
            )

        self.assertNotIn(remote_key, json.dumps(result))
        self.assertEqual(
            remote_key,
            store.saved[('trevor.clients', 'local-admin-api-key')],
        )
        self.assertIn('tools/issue_trevor_api_key.py', ' '.join(commands[0]))
        self.assertIn('--service-user trevor', ' '.join(commands[0]))
        self.assertNotIn(remote_key, ' '.join(commands[0]))


if __name__ == '__main__':
    unittest.main()
