import unittest
from unittest.mock import patch
from liveclip.model import Client, decode_json

class ModelTests(unittest.TestCase):
    def test_default_is_deepseek(self):
        client = Client()
        self.assertEqual(client.model, 'deepseek-flash')
        self.assertEqual(client.key_env, 'DEEPSEEK_API_KEY')

    def test_local_file_key_is_available(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'key'
            path.write_text('test-only-secret\n')
            with patch.dict('os.environ', {}, clear=True), patch('liveclip.model.DEEPSEEK_KEY_FILE', path):
                self.assertEqual(Client().get_key(), 'test-only-secret')

    def test_missing_key_stops_before_request(self):
        with patch.dict('os.environ', {}, clear=True), patch('urllib.request.urlopen') as request:
            with self.assertRaises(RuntimeError):
                Client('doubao').review('test')
            request.assert_not_called()

    def test_invalid_json_fails_closed(self):
        for value in ['not json', '[]', '{"clips": NaN}']:
            with self.assertRaises(ValueError): decode_json(value)

    def test_known_provider_required(self):
        with self.assertRaises(ValueError): Client('unknown')

    def test_json_object(self):
        self.assertEqual(decode_json('{"clips": []}'), {'clips': []})
