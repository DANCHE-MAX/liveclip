import tempfile, threading, time, unittest
from pathlib import Path
from liveclip.download_wait import snapshot, wait_for_download

class DownloadWaitTests(unittest.TestCase):
 def test_detects_new_completed_matching_file(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); before=snapshot(root)
   def write():
    temp=root/'sample 2026-11-18 15_40-15_46.mp4.crdownload';temp.write_bytes(b'partial');time.sleep(.12);temp.rename(root/'sample 2026-11-18 15_40-15_46.mp4')
   t=threading.Thread(target=write);t.start()
   result=wait_for_download(root,before,'2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00',timeout=2,poll=.03,stable_checks=3)
   t.join();self.assertEqual(result.name,'sample 2026-11-18 15_40-15_46.mp4')
 def test_existing_and_partial_not_treated_as_complete(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'sample 2026-11-18 15_40-15_46.mp4').write_bytes(b'old');before=snapshot(root);(root/'other 2026-11-18 15_40-15_46.mp4.crdownload').write_bytes(b'part')
   with self.assertRaises(TimeoutError):wait_for_download(root,before,'2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00',timeout=.15,poll=.02,stable_checks=2)
 def test_ambiguity_stops(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);before=snapshot(root)
   for n in ('a','b'):(root/f'{n} 2026-11-18 15_40-15_46.mp4').write_bytes(b'data')
   with self.assertRaises(ValueError):wait_for_download(root,before,'2026-11-18T15:40:00+08:00','2026-11-18T15:46:00+08:00',timeout=.3,poll=.02,stable_checks=2)
