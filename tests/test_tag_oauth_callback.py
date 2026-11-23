import importlib.util
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, urlencode
from urllib.request import build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class CallbackTest(unittest.TestCase):
    def test_duplicate_callback_exchanges_once_and_invalid_state_does_not_consume(self):
        spec = importlib.util.spec_from_file_location('tag_service', 'scripts/tag_oauth/service.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        calls = []
        mod._exchange_auth_code = lambda code: (calls.append(code) or {'code': 0})
        server = ThreadingHTTPServer(('127.0.0.1', 0), mod.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f'http://127.0.0.1:{server.server_port}'
        opener = build_opener(NoRedirect)
        try:
            try:
                opener.open(root + '/start')
            except Exception as redirect:
                state = parse_qs(urlparse(redirect.headers['Location']).query)['state'][0]
            from urllib.error import HTTPError
            from urllib.request import urlopen
            def callback(st):
                return urlopen(root + '/callback?' + urlencode({'state': st, 'auth_code': 'test-code', 'material_auth_status': '1'})).read()
            with self.assertRaises(HTTPError):
                callback('wrong')
            self.assertEqual(json.loads(callback(state))['code'], 0)
            self.assertEqual(json.loads(callback(state))['code'], 0)
            self.assertEqual(calls, ['test-code'])
            self.assertEqual(json.loads(urlopen(root + '/callback-status').read())['code'], 0)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
