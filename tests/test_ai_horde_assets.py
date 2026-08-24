import tempfile
import os
import time
import unittest
from pathlib import Path


class AIHordeAssetTests(unittest.TestCase):
    def test_private_and_non_https_sources_are_rejected(self):
        from core.ai_horde_assets import AIHordeAssetError, AIHordeAssetStore

        with tempfile.TemporaryDirectory() as tmp:
            store = AIHordeAssetStore(
                Path(tmp),
                resolver=lambda _host: ['127.0.0.1'],
                fetcher=lambda _url, _limit: (b'png', 'image/png', '127.0.0.1'),
            )
            with self.assertRaises(AIHordeAssetError):
                store.save_remote('https://images.example/result.png')
            with self.assertRaises(AIHordeAssetError):
                store.save_remote('http://images.example/result.png')

    def test_verified_image_is_saved_under_uuid_and_read_safely(self):
        from core.ai_horde_assets import AIHordeAssetStore

        png = b'\x89PNG\r\n\x1a\n' + b'x' * 32
        with tempfile.TemporaryDirectory() as tmp:
            store = AIHordeAssetStore(
                Path(tmp),
                resolver=lambda _host: ['203.0.113.10'],
                fetcher=lambda _url, _limit: (png, 'image/png', '203.0.113.10'),
                allow_test_networks=True,
            )

            asset = store.save_remote('https://images.example/result.png')
            body, content_type = store.read_asset(asset['asset_id'])

            self.assertEqual(png, body)
            self.assertEqual('image/png', content_type)
            self.assertEqual(f"/api/ai-horde/assets/{asset['asset_id']}", asset['url'])
            self.assertNotIn('images.example', str(asset))
            self.assertNotIn('result.png', str(asset))
            self.assertIsNone(store.read_asset('not-a-uuid'))

            restarted = AIHordeAssetStore(Path(tmp), allow_test_networks=True)
            restarted_body, restarted_type = restarted.read_asset(asset['asset_id'])

            self.assertEqual(png, restarted_body)
            self.assertEqual('image/png', restarted_type)

    def test_content_type_and_size_limits_are_enforced(self):
        from core.ai_horde_assets import AIHordeAssetError, AIHordeAssetStore

        with tempfile.TemporaryDirectory() as tmp:
            invalid = AIHordeAssetStore(
                Path(tmp),
                resolver=lambda _host: ['8.8.8.8'],
                fetcher=lambda _url, _limit: (b'<html>', 'text/html', '8.8.8.8'),
            )
            with self.assertRaises(AIHordeAssetError):
                invalid.save_remote('https://images.example/result')

    def test_expired_assets_are_removed_during_restart(self):
        from core.ai_horde_assets import AIHordeAssetStore

        png = b'\x89PNG\r\n\x1a\n' + b'x' * 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = AIHordeAssetStore(
                root,
                resolver=lambda _host: ['203.0.113.10'],
                fetcher=lambda _url, _limit: (png, 'image/png', '203.0.113.10'),
                allow_test_networks=True,
            )
            asset = store.save_remote('https://images.example/result.png')
            path = next((root / 'ai_horde' / 'assets').glob(f"{asset['asset_id']}.*"))
            expired = time.time() - (25 * 60 * 60)
            os.utime(path, (expired, expired))

            restarted = AIHordeAssetStore(root, allow_test_networks=True)

            self.assertIsNone(restarted.read_asset(asset['asset_id']))
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
