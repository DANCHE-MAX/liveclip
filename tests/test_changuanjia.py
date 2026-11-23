import unittest
from liveclip.changuanjia import pick_latest_ended_stream

class LiveListTests(unittest.TestCase):
    def test_picks_latest_ended_not_current_stream(self):
        state='''604 link 当前直播, Value: changuanjia.com/console/123
605 文本 2026/11/19 10:56
628 link 已结束, Value: changuanjia.com/analyse/456
629 文本 2026/11/17 19:45
650 link 更早, Value: changuanjia.com/analyse/789
651 文本 2026/11/15 11:37'''
        self.assertEqual(pick_latest_ended_stream(state)['stream_id'],'456')
    def test_fails_closed_without_date_or_ended_stream(self):
        with self.assertRaises(ValueError): pick_latest_ended_stream('604 link 当前, Value: changuanjia.com/console/123')
