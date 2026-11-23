import unittest
from liveclip.peak_windows import plan_windows

class PeakWindowTests(unittest.TestCase):
 def test_nearby_peaks_share_one_window(self):
  peaks=[{'time':'2026-11-19T16:00:00+08:00','sales':1000},{'time':'2026-11-19T16:04:00+08:00','sales':900},{'time':'2026-11-19T16:10:00+08:00','sales':800}]
  out=plan_windows(peaks)
  self.assertEqual(len(out),2);self.assertEqual(len(out[0]['peaks']),2)
  self.assertEqual(out[0]['start'],'2026-11-19T15:59:00+08:00');self.assertEqual(out[0]['end'],'2026-11-19T16:05:00+08:00')
 def test_existing_window_is_reused(self):
  peaks=[{'time':'2026-11-19T16:04:00+08:00','sales':900}]
  out=plan_windows(peaks,[{'start':'2026-11-19T16:00:00+08:00','end':'2026-11-19T16:06:00+08:00','path':'/tmp/clip','verified':True}])
  self.assertEqual(out[0]['path'],'/tmp/clip');self.assertEqual(out[0]['action'],'reuse')
 def test_rejects_unverified_and_naive(self):
  with self.assertRaises(ValueError):plan_windows([{'time':'2026-11-19T16:04:00','sales':900}])
  with self.assertRaises(ValueError):plan_windows([{'time':'2026-11-19T16:04:00+08:00','sales':None}])
