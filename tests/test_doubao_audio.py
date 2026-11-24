import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from liveclip.model import Client


class DoubaoAudioTests(unittest.TestCase):
    def test_local_ark_key_and_seed21_default(self):
        import liveclip.model as model
        with tempfile.TemporaryDirectory() as d:
            key = Path(d) / 'key'
            key.write_text('test-only-ark-key')
            with patch.dict('os.environ', {}, clear=True), patch.object(model, 'ARK_KEY_FILE', key, create=True):
                self.assertEqual(Client('doubao').get_key(), 'test-only-ark-key')
                self.assertEqual(Client('doubao').model, 'doubao-seed-2-1-lite-260915')

    def test_one_request_cached_and_never_sent_to_deepseek(self):
        from liveclip.doubao_audio import review_cached
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); wav=root/'audio.wav'; wav.write_bytes(b'test audio')
            response={'id':'r1','status':'completed','model':'doubao-seed-2-1-lite-260915',
                      'output':[{'content':[{'type':'output_text','text':'{"clips":[]}'}]}],
                      'usage':{'input_tokens':10,'output_tokens':3}}
            with patch.dict('os.environ', {'ARK_API_KEY':'test-only-ark-key'}), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as send:
                self.assertEqual(review_cached(Client('doubao'), 'select', wav, root/'cache'), {'clips':[]})
                self.assertEqual(review_cached(Client('doubao'), 'select', wav, root/'cache'), {'clips':[]})
                self.assertEqual(send.call_count, 1)
                req=send.call_args.args[0]
                self.assertEqual(req.full_url, 'https://ark.cn-beijing.volces.com/api/v3/responses')
                body=json.loads(req.data)
                self.assertTrue(body['input'][0]['content'][0]['audio_url'].startswith('data:audio/wav;base64,'))
                self.assertNotIn('deepseek', req.full_url)

    def test_unknown_result_blocks_second_submission(self):
        from liveclip.doubao_audio import review_cached
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); wav=root/'audio.wav'; wav.write_bytes(b'audio')
            with patch.dict('os.environ', {'ARK_API_KEY':'test-only-ark-key'}), patch('urllib.request.urlopen', side_effect=TimeoutError()) as send:
                with self.assertRaises(RuntimeError): review_cached(Client('doubao'), 'select', wav, root/'cache')
                with self.assertRaises(RuntimeError): review_cached(Client('doubao'), 'select', wav, root/'cache')
                self.assertEqual(send.call_count,1)

    def test_text_selection_does_not_resend_audio_and_schema_is_explicit(self):
        from liveclip.doubao_audio import review_cached
        result={'id':'r2','status':'completed','model':'doubao-seed-2-1-lite-260915',
                'output':[{'content':[{'type':'output_text','text':'{"clips":[]}'}]}]}
        schema={'type':'object','properties':{'clips':{'type':'array','items':{'type':'string'}}},'required':['clips'],'additionalProperties':False}
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {'ARK_API_KEY':'test-only-ark-key'}), patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(result).encode())) as send:
            self.assertEqual(review_cached(Client('doubao'),'select transcript only',None,Path(d),schema=schema),{'clips':[]})
            body=json.loads(send.call_args.args[0].data)
            self.assertEqual([x['type'] for x in body['input'][0]['content']],['input_text'])
            self.assertEqual(body['text']['format']['type'],'json_schema')
            self.assertTrue(body['text']['format']['strict'])

    def test_deepseek_client_rejected_before_transmitting_ark_audio(self):
        from liveclip.doubao_audio import review_cached
        with patch('urllib.request.urlopen') as send:
            with self.assertRaises(ValueError): review_cached(Client('deepseek'), 'x', Path('unused'), Path('unused'))
            send.assert_not_called()


if __name__=='__main__': unittest.main()
