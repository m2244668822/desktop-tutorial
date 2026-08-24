import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AutonomyDaemonContractTests(unittest.TestCase):
    def test_module_import_does_not_load_task_executor(self):
        repository_root = Path(__file__).resolve().parents[1]
        process = subprocess.run(
            [
                sys.executable,
                '-c',
                (
                    'import sys; '
                    'import tools.agent_autonomy_daemon; '
                    "print('core.autonomy_executor' in sys.modules)"
                ),
            ],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual('False', process.stdout.strip())

    def test_idle_daemon_does_not_load_task_executor(self):
        repository_root = Path(__file__).resolve().parents[1]
        script = """
import os
import sys
import tempfile

with tempfile.TemporaryDirectory() as data_root:
    os.environ['TREVOR_DATA_DIR'] = data_root
    from tools import agent_autonomy_daemon

    agent_autonomy_daemon.load_signals = lambda *args, **kwargs: {
        'quota_sufficient': True,
        'services_healthy': True,
        'user_active': False,
        'cpu_percent': 0.0,
        'memory_percent': 0.0,
    }
    agent_autonomy_daemon.skill_stability = lambda *args, **kwargs: {
        'stable': True,
        'conflict_count': 0,
        'conflicts': [],
    }
    agent_autonomy_daemon.run_daemon(
        agent_autonomy_daemon.parse_args(['--once', '--worker-only'])
    )
    print('core.autonomy_executor' in sys.modules)
"""
        process = subprocess.run(
            [sys.executable, '-c', script],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual('False', process.stdout.strip())

    def test_defaults_match_trevor_schedule(self):
        from tools import agent_autonomy_daemon

        args = agent_autonomy_daemon.parse_args([])

        self.assertEqual(60, args.heartbeat)
        self.assertEqual(900, args.evaluation)

    def test_nvidia_quota_or_payment_failure_pauses_tasks(self):
        from tools.agent_autonomy_daemon import provider_signals

        signals = provider_signals(
            {
                'providers': [
                    {
                        'provider': 'nvidia',
                        'enabled': False,
                        'disabled_reason': 'quota_exhausted',
                        'quota': {'state': 'exhausted'},
                    }
                ]
            }
        )

        self.assertFalse(signals['quota_sufficient'])
        self.assertFalse(signals['services_healthy'])

    def test_scheduler_and_worker_modes_are_mutually_exclusive(self):
        from tools import agent_autonomy_daemon

        scheduler = agent_autonomy_daemon.parse_args(['--scheduler-only'])
        worker = agent_autonomy_daemon.parse_args(['--worker-only'])

        self.assertTrue(scheduler.scheduler_only)
        self.assertFalse(scheduler.worker_only)
        self.assertTrue(worker.worker_only)
        with self.assertRaises(SystemExit):
            agent_autonomy_daemon.parse_args(['--scheduler-only', '--worker-only'])

    def test_public_provider_status_uses_loopback_endpoint(self):
        from tools.agent_autonomy_daemon import load_public_provider_status

        requested = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exception_type, exception, traceback):
                return False

            def read(self):
                return json.dumps({'ok': True, 'providers': []}).encode('utf-8')

        def opener(request, timeout):
            requested['url'] = request.full_url
            requested['timeout'] = timeout
            return Response()

        payload = load_public_provider_status(opener=opener)

        self.assertEqual('http://127.0.0.1:5001/api/trevor/providers', requested['url'])
        self.assertEqual(5.0, requested['timeout'])
        self.assertEqual([], payload['providers'])

    def test_load_signals_does_not_read_keychain(self):
        from core.autonomy import AutonomyConfig
        from tools.agent_autonomy_daemon import load_signals

        status = {
            'providers': [
                {
                    'provider': 'nvidia',
                    'enabled': True,
                    'disabled_reason': '',
                    'quota': {'state': 'available'},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                'core.keychain_credentials.KeychainCredentialStore.get_secret',
                side_effect=AssertionError('keychain_must_not_be_read'),
            ):
                signals = load_signals(
                    Path(temporary_directory),
                    AutonomyConfig(),
                    provider_status_loader=lambda: status,
                )

        self.assertTrue(signals['quota_sufficient'])
        self.assertTrue(signals['services_healthy'])


if __name__ == '__main__':
    unittest.main()
