import unittest


class _Store:
    def authenticate(self, api_key, *, required_scope):
        if api_key == 'valid' and required_scope in {'audit', 'chat'}:
            return {'ok': True, 'key_id': 'key-1'}
        return {'ok': False, 'error': 'scope_denied'}


class WebScopeAuthTests(unittest.TestCase):
    def test_bearer_and_x_api_token_are_scope_checked(self):
        from core.web_server import WebServerMode

        server = WebServerMode.__new__(WebServerMode)
        server.api_key_store = _Store()

        bearer = server.authorize_headers({'Authorization': 'Bearer valid'}, 'audit')
        token = server.authorize_headers({'X-API-Token': 'valid'}, 'audit')
        cookie = server.authorize_headers(
            {'Cookie': 'theme=dark; trevor_session=valid'}, 'chat'
        )
        denied = server.authorize_headers({'Authorization': 'Bearer wrong'}, 'audit')

        self.assertTrue(bearer['ok'])
        self.assertTrue(token['ok'])
        self.assertTrue(cookie['ok'])
        self.assertEqual('scope_denied', denied['error'])

    def test_missing_auth_store_fails_closed(self):
        from core.web_server import WebServerMode

        server = WebServerMode.__new__(WebServerMode)
        server.api_key_store = None

        result = server.authorize_headers({}, 'users')

        self.assertEqual({'ok': False, 'error': 'auth_not_configured'}, result)


if __name__ == '__main__':
    unittest.main()
