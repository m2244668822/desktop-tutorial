import unittest
from unittest.mock import patch
from urllib.parse import unquote


class _HtmlResponse:
    def __init__(self, html):
        self.html = html

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.html.encode('utf-8')


class _RequestsResponse:
    status_code = 200

    def __init__(self, html):
        self.content = html.encode('utf-8')

    def raise_for_status(self):
        return None


class WebSearchAdapterTests(unittest.TestCase):
    def test_default_transport_uses_browser_compatible_requests_session(self):
        from core.web_search import WebSearchAdapter

        response = _RequestsResponse(
            '''
            <a class="result__a" href="https://example.com/verified">Verified</a>
            <a class="result__snippet">Browser-compatible result.</a>
            '''
        )
        with patch('core.web_search.requests.get', return_value=response) as get:
            result = WebSearchAdapter(timeout=6).search('Trevor status', limit=1)

        self.assertTrue(result['ok'])
        self.assertEqual(6, get.call_args.kwargs['timeout'])
        self.assertIn('Mozilla/5.0', get.call_args.kwargs['headers']['User-Agent'])

    def test_search_redacts_private_query_and_returns_normalized_results(self):
        from core.web_search import WebSearchAdapter

        opened = []

        def opener(request, timeout):
            opened.append((request, timeout))
            return _HtmlResponse(
                '''
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftrevor">Trevor Result</a>
                <a class="result__snippet">Current verified summary.</a>
                '''
            )

        adapter = WebSearchAdapter(opener=opener, timeout=4)
        result = adapter.search(
            'owner@example.com API_KEY=super-secret Trevor status',
            limit=3,
        )

        request, timeout = opened[0]
        requested_url = unquote(request.full_url)
        self.assertNotIn('owner@example.com', requested_url)
        self.assertNotIn('super-secret', requested_url)
        self.assertEqual(4, timeout)
        self.assertTrue(result['ok'])
        self.assertEqual('https://example.com/trevor', result['results'][0]['url'])
        self.assertEqual('Trevor Result', result['results'][0]['title'])
        self.assertEqual('Current verified summary.', result['results'][0]['snippet'])


if __name__ == '__main__':
    unittest.main()
