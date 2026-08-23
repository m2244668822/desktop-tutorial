import json
import unittest


class ExternalContentSanitizerTests(unittest.TestCase):
    def test_secrets_pii_paths_and_attachments_are_redacted(self):
        from core.content_sanitizer import ExternalContentSanitizer

        sanitizer = ExternalContentSanitizer()
        result = sanitizer.sanitize(
            message=(
                '寄給 owner@example.com，NVIDIA_API_KEY=nvapi-super-secret-value，'
                '讀取 /Users/owner/private/note.txt，電話 +886 912-345-678。'
            ),
            conversation=[{'role': 'user', 'content': 'Bearer abc.def.ghi'}],
            memory_context='密碼 password=hunter2',
            attachments=[{'name': 'private.png', 'url': 'file:///Users/owner/private.png', 'data': 'base64-secret'}],
        )
        rendered = json.dumps(result.payload, ensure_ascii=False)

        for private_value in (
            'owner@example.com',
            'nvapi-super-secret-value',
            '/Users/owner/private/note.txt',
            '+886 912-345-678',
            'abc.def.ghi',
            'hunter2',
            'base64-secret',
            'file:///Users/owner/private.png',
        ):
            self.assertNotIn(private_value, rendered)
        self.assertEqual('private.png', result.payload['attachments'][0]['name'])
        self.assertNotIn('url', result.payload['attachments'][0])
        self.assertGreaterEqual(result.redaction_count, 6)

    def test_external_payload_has_no_tools_or_mutating_interfaces(self):
        from core.content_sanitizer import ExternalContentSanitizer

        result = ExternalContentSanitizer().sanitize(
            message='分析這段內容',
            tool_definitions=[{'name': 'git_commit'}],
            autonomy={'create_task': True},
            memory_write={'enabled': True},
        )

        self.assertNotIn('tools', result.payload)
        self.assertNotIn('tool_definitions', result.payload)
        self.assertNotIn('autonomy', result.payload)
        self.assertNotIn('memory_write', result.payload)


if __name__ == '__main__':
    unittest.main()
