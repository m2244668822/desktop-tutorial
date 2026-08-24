import subprocess
import unittest


class TailscaleStatusTests(unittest.TestCase):
    def test_macos_network_extension_reports_connected_without_linux_socket(self):
        from core.network_status import tailscale_status

        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, stdout='Connected\n', stderr='')

        status = tailscale_status(system_name='Darwin', runner=runner, env={})

        self.assertTrue(status['configured'])
        self.assertTrue(status['connected'])
        self.assertEqual(['/usr/sbin/scutil', '--nc', 'status', 'Tailscale'], calls[0][0])
        self.assertEqual(2, calls[0][1]['timeout'])

    def test_disconnected_macos_profile_is_configured_but_not_connected(self):
        from core.network_status import tailscale_status

        def runner(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, stdout='Disconnected\n', stderr='')

        status = tailscale_status(system_name='Darwin', runner=runner, env={})

        self.assertTrue(status['configured'])
        self.assertFalse(status['connected'])


if __name__ == '__main__':
    unittest.main()
