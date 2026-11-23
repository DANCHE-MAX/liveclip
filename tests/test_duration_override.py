import unittest
from liveclip.__main__ import valid_source_duration

class DurationOverrideTests(unittest.TestCase):
 def test_relative_window_is_explicit_and_bounded(self):
  self.assertFalse(valid_source_duration(363.108667, False))
  self.assertTrue(valid_source_duration(363.108667, True))
  self.assertFalse(valid_source_duration(370, True))
  self.assertFalse(valid_source_duration(None, True))
