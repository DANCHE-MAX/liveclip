import unittest
from liveclip.handoff import validate_window

class HandoffTests(unittest.TestCase):
    def test_authorized_export_padding_uses_relative_timeline(self):
        args=('2026-11-21T00:27:00+08:00','2026-11-21T00:24:00+08:00','2026-11-21T00:30:00+08:00')
        with self.assertRaises(ValueError): validate_window(*args,363.104667)
        result=validate_window(*args,363.104667,relative_window=True)
        self.assertEqual(result['timing_mode'],'relative_media_only')
        self.assertEqual(result['media_duration'],363.104667)
        with self.assertRaises(ValueError): validate_window(*args,370,relative_window=True)
        with self.assertRaises(ValueError): validate_window(args[0],args[1],'2026-11-21T00:31:00+08:00',363.104667,relative_window=True)
    def test_accepts_exact_centered_window_and_duration(self):
        result=validate_window('2026-11-18T15:43:00+08:00','2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00',360.8)
        self.assertEqual(result['window_seconds'],360)
    def test_rejects_wrong_center(self):
        with self.assertRaises(ValueError): validate_window('2026-11-18T15:43:00+08:00','2026-11-18T15:39:00+08:00','2026-11-18T15:45:00+08:00',360)
    def test_rejects_bad_duration_and_timezone(self):
        with self.assertRaises(ValueError): validate_window('2026-11-18T15:43:00+08:00','2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00',350)
        with self.assertRaises(ValueError): validate_window('2026-11-18T15:43:00','2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00',360)

class FilenameTests(unittest.TestCase):
    def test_filename_matches_observed_date_and_range(self):
        from liveclip.handoff import validate_download_name
        validate_download_name('店铺 2026-11-18 15_40-15_46 (1).mp4','2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00')
    def test_rejects_wrong_date_or_window(self):
        from liveclip.handoff import validate_download_name
        with self.assertRaises(ValueError): validate_download_name('店铺 2026-11-17 15_40-15_46.mp4','2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00')
        with self.assertRaises(ValueError): validate_download_name('店铺 2026-11-18 15_39-15_45.mp4','2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00')
