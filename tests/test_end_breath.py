import unittest
from liveclip.end_breath import choose_end

class EndBreathTests(unittest.TestCase):
 def test_half_second_when_silence_covers_target(self):
  self.assertAlmostEqual(choose_end(10.0,[(9.95,10.9)],20,0),10.5)
 def test_trim_before_next_utterance(self):
  self.assertLess(choose_end(10,[(10.1,10.4)],20,0,next_start=10.4),10.4)
 def test_no_gap_fails_closed(self):
  with self.assertRaises(ValueError):choose_end(10,[(11,12)],20,0)
 def test_never_beyond_30_seconds(self):
  self.assertLessEqual(choose_end(29.8,[(29.8,30.5)],40,0),30)
 def test_later_gap_after_next_sentence_is_not_used(self):
  with self.assertRaises(ValueError):choose_end(10,[(10.6,11)],20,0,next_start=10.2)

class AudioGapTests(unittest.TestCase):
 def test_detects_actual_audio_pause(self):
  import math,tempfile,wave,struct
  from pathlib import Path
  from liveclip.end_breath import detect_gaps
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'sample.wav';rate=16000
   with wave.open(str(p),'wb') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
    samples=[int(10000*math.sin(2*math.pi*220*i/rate)) if i<rate or i>=int(1.8*rate) else 0 for i in range(3*rate)]
    w.writeframes(struct.pack('<'+'h'*len(samples),*samples))
   gaps=detect_gaps(p,1.0,3.0)
   end=choose_end(1.0,gaps,3.0,0)
   self.assertAlmostEqual(end,1.5,places=1)
