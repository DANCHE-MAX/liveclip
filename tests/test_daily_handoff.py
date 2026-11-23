import tempfile, unittest
from pathlib import Path
from unittest.mock import Mock
from liveclip.daily_delivery import send_lark_file

class LarkDeliveryTests(unittest.TestCase):
 def test_send_uses_private_file_message_and_stable_idempotency(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'day.zip';p.write_bytes(b'zip')
   run=Mock(return_value=Mock(returncode=0,stdout='{"ok":true,"data":{"message_id":"om_123"}}',stderr=''))
   result=send_lark_file(p,'ou_recipient','key',runner=run)
   self.assertEqual(result,'om_123')
   argv=run.call_args.args[0]
   self.assertIn('--file',argv);self.assertIn('--as',argv);self.assertIn('user',argv);self.assertIn('--idempotency-key',argv)
   self.assertEqual(run.call_args.kwargs['cwd'],str(p.parent.resolve()))
 def test_oversized_archive_stops_before_cli(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'day.zip'
   with p.open('wb') as f:f.truncate(30*1024*1024+1)
   run=Mock()
   with self.assertRaises(ValueError):send_lark_file(p,'ou_recipient','key',runner=run)
   run.assert_not_called()

class PrepareTests(unittest.TestCase):
 def test_shortfall_reports_count_without_creating_zip(self):
  from liveclip.daily_job import prepare_daily
  import json
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'clips').mkdir();(root/'clips/clip_01.mp4').write_bytes(b'one')
   (root/'review_report.json').write_text(json.dumps({'status':'complete','accepted':[{'start':0,'end':18}]}))
   result=prepare_daily([root/'review_report.json'],root/'out.zip')
   self.assertEqual(result['status'],'insufficient_clips');self.assertEqual(result['count'],1)
   self.assertFalse((root/'out.zip').exists())

class UploadGateTests(unittest.TestCase):
 def test_both_accounts_must_have_every_file_confirmed(self):
  import hashlib
  from liveclip.daily_job import all_uploaded
  from liveclip.plain_upload import PlainQueue
  import sqlite3
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'x.mp4';p.write_bytes(b'one');sha=hashlib.sha256(b'one').hexdigest();q=PlainQueue(root/'q.db')
   for a in ('a','b'):q.add(a,p,sha)
   with sqlite3.connect(q.path) as db:db.execute("update tasks set status='confirmed' where account='a'")
   self.assertFalse(all_uploaded([p],q.path,('a','b')))
   with sqlite3.connect(q.path) as db:db.execute("update tasks set status='confirmed' where account='b'")
   self.assertTrue(all_uploaded([p],q.path,('a','b')))
