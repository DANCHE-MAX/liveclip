import json
import tempfile
import unittest
from pathlib import Path
from liveclip.existing import validate_sources

class ExistingTests(unittest.TestCase):
    def test_missing_file_is_failure(self):
        with self.assertRaises(FileNotFoundError):
            validate_sources([{'path': '/nonexistent/video.mp4', 'peak': '2026-11-18T13:26:00+08:00'}])
    def test_requires_identified_peak_and_regular_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source.mp4'; p.write_bytes(b'test')
            with self.assertRaises(ValueError): validate_sources([{'path': str(p)}])
            self.assertEqual(validate_sources([{'path': str(p), 'peak': '2026-11-18T13:26:00+08:00'}])[0]['path'],str(p.resolve()))
