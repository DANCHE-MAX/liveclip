import unittest
from datetime import datetime,timedelta,timezone
from liveclip.hourly_peaks import select_hour

class HourlyPeakTests(unittest.TestCase):
 def samples(self):
  start=datetime(2026,11,20,14,tzinfo=timezone(timedelta(hours=8)))
  return [{'time':(start+timedelta(minutes=i)).isoformat(),'sales':0} for i in range(60)]
 def test_fallback_selects_maximum_at_least_600(self):
  rows=self.samples();rows[2]['sales']=870.2;rows[12]['sales']=827
  self.assertEqual(select_hour(rows,rows[0]['time'])[0]['sales'],870.2)
 def test_threshold_returns_all_high_points(self):
  rows=self.samples();rows[2]['sales']=1000;rows[12]['sales']=1200
  self.assertEqual(len(select_hour(rows,rows[0]['time'])),2)
 def test_no_peak_below_600(self):
  rows=self.samples();rows[4]['sales']=599
  self.assertEqual(select_hour(rows,rows[0]['time']),[])
 def test_incomplete_hour_blocks_selection(self):
  rows=self.samples();rows[2]['sales']=900
  with self.assertRaises(ValueError):select_hour(rows[:-1],rows[0]['time'])
