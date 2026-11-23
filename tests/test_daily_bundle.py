import json,tempfile,unittest,zipfile
from pathlib import Path
from liveclip.daily_bundle import build_bundle

class BundleTests(unittest.TestCase):
 def test_fifty_distinct_clips_are_bundled_with_manifest(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);clips=[]
   for i in range(50):
    p=root/f'{i}.mp4';p.write_bytes(f'video{i}'.encode());clips.append(p)
   result=build_bundle(clips,root/'daily.zip',probe=lambda p: {'duration':18,'video':True,'audio':True})
   self.assertEqual(result['count'],50)
   with zipfile.ZipFile(root/'daily.zip') as z:
    self.assertEqual(len([n for n in z.namelist() if n.endswith('.mp4')]),50)
    self.assertEqual(len(json.loads(z.read('manifest.json'))['clips']),50)
    self.assertIsNone(z.testzip())
 def test_under_target_or_duplicate_never_creates_bundle(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'one.mp4';p.write_bytes(b'video')
   with self.assertRaises(ValueError):build_bundle([p]*50,root/'daily.zip',probe=lambda p:{'duration':18,'video':True,'audio':True})
   self.assertFalse((root/'daily.zip').exists())
 def test_long_video_never_creates_bundle(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);clips=[]
   for i in range(50):
    p=root/f'{i}.mp4';p.write_bytes(str(i).encode());clips.append(p)
   with self.assertRaises(ValueError):build_bundle(clips,root/'daily.zip',probe=lambda p:{'duration':30.01,'video':True,'audio':True})
   self.assertFalse((root/'daily.zip').exists())

class DailyWindowTests(unittest.TestCase):
 def test_eleven_six_minute_windows_are_supported(self):
  from liveclip.job import run_windows
  windows=[{'id':i} for i in range(11)]
  result=run_windows(windows,lambda w:'source',lambda *_:'complete',limit=11,stop_on_complete=False)
  self.assertEqual(len(result['windows']),11)
 def test_more_than_eleven_rejected(self):
  from liveclip.job import run_windows
  with self.assertRaises(ValueError):run_windows([],lambda w:None,lambda *_:'complete',limit=12)

class SelectionTests(unittest.TestCase):
 def test_collects_only_completed_reports_and_prefers_15_to_20_seconds(self):
  from liveclip.daily_bundle import select_daily
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for n,status in enumerate(('complete','needs_transcript_review')):
    folder=root/str(n);(folder/'clips').mkdir(parents=True)
    (folder/'review_report.json').write_text(json.dumps({'status':status,'accepted':[{'start':0,'end':18}]}))
    (folder/'clips/clip_01.mp4').write_bytes(str(n).encode())
   rows=select_daily([root/'0/review_report.json',root/'1/review_report.json'])
   self.assertEqual(len(rows),1);self.assertEqual(rows[0].parent.parent.name,'0')

class DeliveryTests(unittest.TestCase):
 def test_unknown_send_result_is_never_resent(self):
  from liveclip.daily_delivery import deliver
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'batch.zip';p.write_bytes(b'zip');calls=[]
   def send(*args):calls.append(args);raise TimeoutError()
   self.assertEqual(deliver(root/'ledger.db','2026-11-19',p,'recipient',send),'uncertain')
   self.assertEqual(deliver(root/'ledger.db','2026-11-19',p,'recipient',send),'uncertain')
   self.assertEqual(len(calls),1)
 def test_success_is_recorded_and_never_resent(self):
  from liveclip.daily_delivery import deliver
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'batch.zip';p.write_bytes(b'zip');calls=[]
   def send(*args):calls.append(1);return 'message-id'
   self.assertEqual(deliver(root/'ledger.db','2026-11-19',p,'recipient',send),'sent')
   self.assertEqual(deliver(root/'ledger.db','2026-11-19',p,'recipient',send),'sent')
   self.assertEqual(len(calls),1)
