import tempfile
import unittest
from pathlib import Path

from core.runtime_capabilities import (
    build_runtime_capability_manifest,
    is_runtime_capability_query,
    render_runtime_capability_reply,
)


class RuntimeCapabilityTruthTests(unittest.TestCase):
    def test_manifest_and_reply_report_runtime_truth_without_model_seat_denials(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            skill_directory = workspace / 'skills' / 'workspace-butler'
            skill_directory.mkdir(parents=True)
            (skill_directory / 'SKILL.md').write_text('# workspace-butler\n', encoding='utf-8')
            (workspace / '.git').mkdir()

            manifest = build_runtime_capability_manifest(
                workspace,
                memory_ready=True,
                provider_status={
                    'providers': [
                        {'provider': 'nvidia', 'enabled': True},
                        {'provider': 'gemini', 'enabled': True},
                    ]
                },
                autonomy_status={'daemon_status': 'running'},
                control_plane_status={
                    'ok': True,
                    'task_forwarding_configured': True,
                },
                web_search_ready=False,
            )
            reply = render_runtime_capability_reply(manifest)

        capabilities = manifest['capabilities']
        self.assertEqual(1, capabilities['skill_packages']['count'])
        self.assertTrue(capabilities['workspace_files']['ready'])
        self.assertTrue(capabilities['external_apis']['ready'])
        self.assertTrue(capabilities['persistent_memory']['ready'])
        self.assertTrue(capabilities['autonomous_tasks']['ready'])
        self.assertTrue(capabilities['control_plane']['ready'])
        self.assertFalse(capabilities['realtime_web_search']['ready'])
        self.assertIn('不是全部能力都只靠模型內建', reply)
        self.assertIn('本機技能包：1', reply)
        self.assertIn('工作區檔案：可用', reply)
        self.assertIn('外部 API：可用', reply)
        self.assertIn('持久記憶：可用', reply)
        self.assertIn('專用即時網頁搜尋：尚未登記', reply)
        self.assertNotIn('缺乏檔案系統存取', reply)
        self.assertNotIn('缺乏外部 API 呼叫', reply)
        self.assertNotIn('缺乏長期記憶持久化', reply)

    def test_capability_status_query_is_not_confused_with_install_command(self):
        self.assertTrue(is_runtime_capability_query('說明技能安裝與缺失能力'))
        self.assertTrue(is_runtime_capability_query('你能不能存取檔案和長期記憶？'))
        self.assertFalse(is_runtime_capability_query('直接幫我安裝 workspace-butler 技能'))


if __name__ == '__main__':
    unittest.main()
