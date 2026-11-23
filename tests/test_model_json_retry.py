import io
import json
import unittest
from unittest.mock import patch
from liveclip.model import Client

def response(content):
    return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':content}}],'usage':{}}).encode())

class JsonRetryTests(unittest.TestCase):
    def test_malformed_model_json_recovers_once(self):
        with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'test-only-secret'}),patch('urllib.request.urlopen',side_effect=[response('not json'),response('{"clips":[]}')]) as call:
            self.assertEqual(Client('deepseek').review('review excerpt'),{'clips':[]})
            self.assertEqual(call.call_count,2)
    def test_persistent_malformed_json_stops_after_two_calls(self):
        with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'test-only-secret'}),patch('urllib.request.urlopen',side_effect=[response('not json'),response('still not json')]) as call:
            with self.assertRaises(ValueError):Client('deepseek').review('review excerpt')
            self.assertEqual(call.call_count,2)

if __name__=='__main__':unittest.main()
