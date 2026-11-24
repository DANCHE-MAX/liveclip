"""Regression coverage for oversized word timestamps and paid-request migration."""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import liveclip.doubao_clips as pipeline
from liveclip.download_registry import DownloadRegistry


class SentenceASRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(b'registered test source')
        self.registry = self.root / 'windows.sqlite3'
        DownloadRegistry(self.registry).register_existing('stream-test', '2026-11-24T00:00:00+00:00', self.source)
        self.output = self.root / 'review'
        self.output.mkdir()
        (self.output / 'source_audio.wav').write_bytes(b'test audio')

    def transcript(self, count=2):
        return {'transcript': '这件衣服的面料柔软，版型宽松，尺码可以按照日常习惯选择。' * 8,
                'segments': [{'id': i, 'start': i * 2, 'end': i * 2 + 1,
                              'text': '这件衣服的面料柔软，版型宽松。'} for i in range(count)]}

    @contextmanager
    def transport(self, decisions=(), incomplete=False):
        bodies = []
        decisions = iter(decisions)

        def send(request, timeout):
            bodies.append(json.loads(request.data))
            response = {'id': 'test-response-' + str(len(bodies)),
                        'model': 'doubao-seed-2-1-lite-260915',
                        'status': 'incomplete' if incomplete else 'completed',
                        'output': [] if incomplete else [{'content': [{'type': 'output_text',
                            'text': json.dumps(next(decisions), ensure_ascii=False)}]}],
                        'usage': {'input_tokens': 10, 'output_tokens': 8000 if incomplete else 100}}
            if incomplete:
                response['incomplete_details'] = {'reason': 'length'}
            return io.BytesIO(json.dumps(response).encode())

        with patch.object(pipeline, 'probe', return_value={'duration': 360}), \
                patch.object(pipeline.subprocess, 'run', return_value=type('Result', (), {'stderr': ''})()), \
                patch.dict('os.environ', {'ARK_API_KEY': 'test-only-key'}), \
                patch('urllib.request.urlopen', side_effect=send):
            yield bodies

    def run_pipeline(self):
        return pipeline.run(self.source, self.output, registry=self.registry)

    def test_source_request_is_bounded_and_completed_run_never_bills_again(self):
        with self.transport([self.transcript(), {'clips': []}]) as requests:
            result = self.run_pipeline()
            self.assertEqual(result['status'], 'no_qualifying_clips')
            self.assertEqual(requests[0]['max_output_tokens'], 8000)
            prompt = requests[0]['input'][0]['content'][-1]['text']
            self.assertIn('100', prompt)
            self.assertIn('逐字', prompt)
            self.assertEqual([x['type'] for x in requests[1]['input'][0]['content']], ['input_text'])
            self.assertEqual(self.run_pipeline()['status'], 'no_qualifying_clips')
            self.assertEqual(len(requests), 2)

    def test_more_than_100_segments_stops_before_selection_or_render(self):
        with self.transport([self.transcript(101), {'clips': []}]) as requests:
            with self.assertRaisesRegex(ValueError, '100'):
                self.run_pipeline()
            self.assertEqual(len(requests), 1)
            self.assertFalse((self.output / 'source_review.json').exists())
            self.assertEqual(json.loads((self.output / 'review_report.json').read_text())['status'], 'failed')

    def test_100_segments_is_accepted_for_validation(self):
        with self.transport([self.transcript(100), {'clips': []}]) as requests:
            self.assertEqual(self.run_pipeline()['status'], 'no_qualifying_clips')
            self.assertEqual(len(requests), 2)

    def test_incomplete_response_is_durable_and_never_automatically_resubmitted(self):
        with self.transport(incomplete=True) as requests:
            with self.assertRaises(ValueError):
                self.run_pipeline()
            with self.assertRaises(RuntimeError):
                self.run_pipeline()
            self.assertEqual(len(requests), 1)
            receipts = [json.loads(p.read_text()) for p in (self.output / 'model_cache').glob('*.json')]
            self.assertEqual(receipts[0]['response']['status'], 'incomplete')
            self.assertEqual(receipts[0]['response']['incomplete_details']['reason'], 'length')

    def test_policy_change_does_not_rebill_legacy_failed_run(self):
        legacy = {'status': 'failed', 'pipeline_revision': 3,
                  'source_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
                  'model': 'doubao-seed-2-1-lite-260915', 'accepted': [], 'rejected': []}
        report = self.output / 'review_report.json'
        report.write_text(json.dumps(legacy))
        before = report.read_bytes()
        with self.transport([self.transcript(), {'clips': []}]) as requests:
            with self.assertRaisesRegex(RuntimeError, 'reconciliation'):
                self.run_pipeline()
            self.assertEqual(requests, [])
        self.assertEqual(report.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

class FinalMediaIdentityTests(unittest.TestCase):
    def test_rendered_hash_is_recorded_for_future_upload_gates(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'clips').mkdir();p=root/'clips/clip_01.mp4';p.write_bytes(b'final media')
            report={'accepted':[{'text':'reviewed speech'}]}
            with patch('liveclip.doubao_clips.media_probe',return_value={'audio':True,'video':True,'duration':19.5}):
                pipeline.record_final_media(report,root)
            self.assertEqual(report['accepted'][0]['sha256'],hashlib.sha256(b'final media').hexdigest())
            self.assertEqual(report['accepted'][0]['final_path'],str(p.resolve()))
    def test_bad_final_media_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'clips').mkdir();(root/'clips/clip_01.mp4').write_bytes(b'media')
            with patch('liveclip.doubao_clips.media_probe',return_value={'audio':False,'video':True,'duration':19}):
                with self.assertRaises(ValueError):pipeline.record_final_media({'accepted':[{}]},root)
