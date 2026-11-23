import unittest
from unittest.mock import Mock
from liveclip.job import run_windows

WINDOWS = [dict(peak='2026-11-18T13:26:00+08:00'), dict(peak='2026-11-18T15:43:00+08:00')]

class JobTests(unittest.TestCase):
    def test_moves_to_next_peak_on_empty_result(self):
        acquire = Mock(side_effect=['one.mp4', 'two.mp4'])
        review = Mock(side_effect=['no_qualifying_clips', 'complete'])
        result = run_windows(WINDOWS, acquire, review)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['windows']), 2)

    def test_error_is_not_empty_and_stops(self):
        acquire = Mock(side_effect=RuntimeError('download failed'))
        result = run_windows(WINDOWS, acquire, Mock())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(acquire.call_count, 1)

    def test_unknown_review_result_fails_closed(self):
        result = run_windows(WINDOWS[:1], Mock(return_value='file'), Mock(return_value='surprise'))
        self.assertEqual(result['status'], 'failed')

    def test_no_windows_is_not_no_qualifying(self):
        self.assertEqual(run_windows([], Mock(), Mock())['status'], 'no_verified_sales_peaks')
    def test_uncertain_transcript_stops_without_treating_as_no_clips(self):
        acquire=Mock(return_value='file')
        result=run_windows(WINDOWS, acquire, Mock(return_value='needs_transcript_review'))
        self.assertEqual(result['status'],'needs_transcript_review')
        self.assertEqual(acquire.call_count,1)
    def test_batch_can_review_ten_windows_without_stopping_at_first_complete(self):
        windows=[{'peak':str(i)} for i in range(10)]
        acquire=Mock(side_effect=[str(i) for i in range(10)])
        result=run_windows(windows,acquire,Mock(return_value='complete'),limit=10,stop_on_complete=False)
        self.assertEqual(len(result['windows']),10);self.assertEqual(acquire.call_count,10);self.assertEqual(result['status'],'complete')
