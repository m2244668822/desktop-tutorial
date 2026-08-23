import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeploymentContractTests(unittest.TestCase):
    def test_systemd_services_are_hardened_and_externalize_data(self):
        service_names = (
            'trevor-api.service',
            'trevor-graphiti.service',
            'trevor-autonomy.service',
            'trevor-worker.service',
        )
        for name in service_names:
            content = (ROOT / 'deploy' / 'systemd' / name).read_text(encoding='utf-8')
            with self.subTest(service=name):
                self.assertIn('User=trevor', content)
                self.assertIn('Environment=TREVOR_DATA_DIR=/var/lib/trevor', content)
                self.assertIn('NoNewPrivileges=true', content)
                self.assertIn('ProtectSystem=strict', content)
                self.assertIn('PrivateTmp=true', content)

        api = (ROOT / 'deploy' / 'systemd' / 'trevor-api.service').read_text(
            encoding='utf-8'
        )
        self.assertIn('LoadCredential=trevor_api_hmac:', api)
        self.assertIn('--host 127.0.0.1', api)

        graphiti = (ROOT / 'deploy' / 'systemd' / 'trevor-graphiti.service').read_text(
            encoding='utf-8'
        )
        self.assertIn('LoadCredential=gemini_api_key:', graphiti)
        self.assertIn('LoadCredential=graphiti_token:', graphiti)

    def test_launchagent_runs_rendered_edge_client(self):
        content = (ROOT / 'deploy' / 'launchd' / 'com.trevor.edge.plist').read_text(
            encoding='utf-8'
        )

        self.assertIn('__TREVOR_ROOT__', content)
        self.assertIn('__TREVOR_REMOTE_URL__', content)
        self.assertIn('trevor_edge_client.py', content)
        self.assertIn('<key>KeepAlive</key>', content)

    def test_required_ci_uses_python_312_tests_and_secret_gate(self):
        content = (ROOT / '.github' / 'workflows' / 'trevor-required.yml').read_text(
            encoding='utf-8'
        )

        self.assertIn("python-version: '3.12'", content)
        self.assertIn('python tools/scan_secrets.py', content)
        self.assertIn('python -m unittest discover', content)
        self.assertIn('name: trevor-required', content)

    def test_systemd_install_records_deployment_in_hash_chain(self):
        content = (ROOT / 'deploy' / 'systemd' / 'install.sh').read_text(
            encoding='utf-8'
        )

        self.assertIn('tools/trevor_operations.py audit', content)
        self.assertIn('--event deployment', content)
        self.assertIn('--data-root "$DATA_ROOT"', content)

    def test_uv_bootstrap_pins_python_312_baseline(self):
        self.assertEqual(
            '3.12',
            (ROOT / '.python-version').read_text(encoding='utf-8').strip(),
        )
        content = (ROOT / 'tools' / 'setup_py312_agent_env.sh').read_text(
            encoding='utf-8'
        )

        self.assertIn('uv venv --python 3.12', content)
        self.assertIn('uv pip sync', content)
        self.assertIn('requirements-ci.lock', content)


if __name__ == '__main__':
    unittest.main()
