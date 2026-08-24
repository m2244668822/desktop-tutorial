import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory


class _Result:
    def __init__(self, value=''):
        self.configured = bool(value)
        self.value = value


class _Store:
    def __init__(self, values):
        self.values = values

    def get_secret(self, service, account):
        return _Result(self.values.get((service, account), ''))


class TrevorBackendLauncherTests(unittest.TestCase):
    def test_runtime_python_path_preserves_virtualenv_symlink(self):
        from tools.launch_trevor_backend import runtime_python_path

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            interpreter = root / 'python3.12'
            interpreter.write_text('', encoding='utf-8')
            virtualenv_python = root / 'venv-python'
            virtualenv_python.symlink_to(interpreter)

            self.assertEqual(virtualenv_python, runtime_python_path(str(virtualenv_python)))

    def test_collects_only_configured_runtime_credentials_with_systemd_names(self):
        from tools.launch_trevor_backend import collect_runtime_credentials

        credentials = collect_runtime_credentials(
            _Store(
                {
                    ('trevor.providers', 'nvidia-api-key'): 'nvidia-secret',
                    ('trevor.providers', 'gemini-api-key'): 'gemini-secret',
                    ('trevor.auth', 'api-key-hmac'): 'hmac-secret',
                    ('trevor.memory', 'aes-256-gcm'): 'memory-secret',
                }
            )
        )

        self.assertEqual('nvidia-secret', credentials['nvidia_api_key'])
        self.assertEqual('gemini-secret', credentials['gemini_api_key'])
        self.assertEqual('hmac-secret', credentials['trevor_api_hmac'])
        self.assertEqual('memory-secret', credentials['trevor_memory_key_b64'])
        self.assertNotIn('groq_api_key', credentials)

    def test_loads_private_file_credentials_without_touching_keychain(self):
        from tools.launch_trevor_backend import load_runtime_credentials

        with TemporaryDirectory() as temporary_directory:
            credential_directory = Path(temporary_directory)
            credential_directory.chmod(0o700)
            credential_file = credential_directory / 'nvidia_api_key'
            credential_file.write_text('nvidia-secret\n', encoding='utf-8')
            credential_file.chmod(0o400)

            with patch(
                'tools.launch_trevor_backend.KeychainCredentialStore',
                side_effect=AssertionError('keychain_must_not_be_opened'),
            ):
                credentials = load_runtime_credentials(credential_directory)

        self.assertEqual({'nvidia_api_key': 'nvidia-secret'}, credentials)

    def test_keychain_import_requires_explicit_opt_in(self):
        from tools.launch_trevor_backend import load_runtime_credentials

        with TemporaryDirectory() as temporary_directory:
            credential_directory = Path(temporary_directory)
            credential_directory.chmod(0o700)
            store = _Store(
                {('trevor.providers', 'nvidia-api-key'): 'nvidia-secret'}
            )

            with patch(
                'tools.launch_trevor_backend.KeychainCredentialStore',
                return_value=store,
            ) as store_factory:
                credentials = load_runtime_credentials(
                    credential_directory,
                    allow_keychain=True,
                )

        store_factory.assert_called_once_with()
        self.assertEqual('nvidia-secret', credentials['nvidia_api_key'])

    def test_rejects_credential_files_visible_to_other_users(self):
        from tools.launch_trevor_backend import load_runtime_credentials

        with TemporaryDirectory() as temporary_directory:
            credential_directory = Path(temporary_directory)
            credential_directory.chmod(0o700)
            credential_file = credential_directory / 'nvidia_api_key'
            credential_file.write_text('nvidia-secret', encoding='utf-8')
            credential_file.chmod(0o644)

            with self.assertRaisesRegex(RuntimeError, 'credential_file_permissions'):
                load_runtime_credentials(credential_directory)
