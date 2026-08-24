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
        for credential in (
            'nvidia_api_key',
            'gemini_api_key',
            'groq_api_key',
            'cerebras_api_key',
            'openrouter_api_key',
            'cloudflare_api_key',
        ):
            self.assertIn(f'LoadCredential={credential}:', api)

        graphiti = (ROOT / 'deploy' / 'systemd' / 'trevor-graphiti.service').read_text(
            encoding='utf-8'
        )
        self.assertIn('LoadCredential=gemini_api_key:', graphiti)
        self.assertIn('LoadCredential=nvidia_api_key:', graphiti)
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
        self.assertIn('Graphiti Linux smoke', content)
        self.assertIn('uv sync --project services/graphiti_sidecar', content)
        self.assertIn('http://127.0.0.1:8091/health', content)

    def test_systemd_install_records_deployment_in_hash_chain(self):
        content = (ROOT / 'deploy' / 'systemd' / 'install.sh').read_text(
            encoding='utf-8'
        )

        self.assertIn('tools/trevor_operations.py audit', content)
        self.assertIn('--event deployment', content)
        self.assertIn('--data-root "$DATA_ROOT"', content)
        self.assertIn('tailscale status >/dev/null 2>&1', content)

    def test_systemd_install_bootstraps_python_and_locked_graphiti_runtime(self):
        content = (ROOT / 'deploy' / 'systemd' / 'install.sh').read_text(
            encoding='utf-8'
        )

        self.assertIn('export PATH="/usr/local/bin:$PATH"', content)
        self.assertIn('PYTHON_ROOT="/opt/trevor/python"', content)
        self.assertIn('UV_PYTHON_INSTALL_DIR="$PYTHON_ROOT"', content)
        self.assertIn('ca-certificates curl gcc gcc-c++ git make rsync', content)
        self.assertIn('build-essential ca-certificates curl git rsync', content)
        self.assertIn('uv python install 3.12', content)
        self.assertEqual(2, content.count('uv venv --python 3.12 --clear'))
        self.assertIn('uv pip install --python', content)
        self.assertIn('--requirements "$BUILD_ROOT/requirements.txt"', content)
        self.assertIn('requirements.txt', content)
        self.assertIn('uv sync --project', content)
        self.assertIn('--frozen --no-dev', content)
        self.assertIn('optional_credentials=', content)
        self.assertLess(
            content.index('cd "$BUILD_ROOT"'),
            content.index('uv python install'),
        )
        self.assertIn('restorecon -RF "$PYTHON_ROOT" "$BUILD_ROOT"', content)
        self.assertIn('restorecon -RF "$APP_ROOT"', content)
        self.assertIn('falkordb-rhel9-x64.so', content)
        self.assertIn(
            '0f8f7ba39a5f5c9bd1a2e270915bb1435369d9413773a91de6bcc84c5b0f2ea7',
            content,
        )
        self.assertIn('sha256sum --check --status', content)
        self.assertIn('systemctl restart trevor-graphiti.service', content)
        self.assertIn('systemctl restart trevor-api.service', content)
        self.assertIn(
            'systemctl restart trevor-autonomy.service trevor-worker.service',
            content,
        )
        self.assertLess(
            content.index('systemctl restart trevor-graphiti.service'),
            content.index('systemctl restart trevor-api.service'),
        )

    def test_systemd_install_builds_before_cutover_and_rolls_back_failure(self):
        content = (ROOT / 'deploy' / 'systemd' / 'install.sh').read_text(
            encoding='utf-8'
        )

        self.assertIn('RELEASE_ROOT="/opt/trevor/releases"', content)
        self.assertIn('BUILD_ROOT=', content)
        self.assertIn('PREVIOUS_APP_ROOT=', content)
        self.assertIn('rollback_cutover()', content)
        self.assertIn('mv "$BUILD_ROOT" "$APP_ROOT"', content)
        self.assertIn('mv "$PREVIOUS_APP_ROOT" "$APP_ROOT"', content)
        self.assertIn('systemctl is-active --quiet "$service"', content)
        self.assertLess(
            content.index('uv sync --project'),
            content.index('CUTOVER_STARTED=1\nsystemctl stop'),
        )

    def test_oci_deploy_has_non_destructive_preflight_mode(self):
        content = (ROOT / 'deploy_to_oci.sh').read_text(encoding='utf-8')

        self.assertIn('--preflight-only', content)
        self.assertIn('preflight=ok', content)
        self.assertIn('IdentitiesOnly=yes', content)

    def test_oci_deploy_resumes_large_syncs_with_tolerant_keepalive(self):
        content = (ROOT / 'deploy_to_oci.sh').read_text(encoding='utf-8')

        self.assertIn('OCI_SSH_SERVER_ALIVE_COUNT_MAX:-12', content)
        self.assertIn("--partial-dir '.rsync-partial'", content)

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
