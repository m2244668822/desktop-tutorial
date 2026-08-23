import unittest


class AutonomyDaemonContractTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
