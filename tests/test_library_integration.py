import hashlib,json,tempfile,unittest
from pathlib import Path
from liveclip.plain_upload import PlainQueue

class LibraryIntegrationTests(unittest.TestCase):
 def test_completed_report_enqueues_each_clip_for_both_accounts_once(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'clips').mkdir();(root/'clips/clip_01.mp4').write_bytes(b'video')
   report=root/'review_report.json';report.write_text(json.dumps({'status':'complete','accepted':[{}]}))
   q=PlainQueue(root/'queue.db');q.stage_report(report,['a','b']);q.stage_report(report,['a','b'])
   self.assertEqual([(r['account'],r['status']) for r in q.rows()],[('a','pending'),('b','pending')])
 def test_rejected_report_cannot_enqueue(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);report=root/'report.json';report.write_text(json.dumps({'status':'needs_transcript_review','accepted':[{}]}))
   q=PlainQueue(root/'queue.db')
   with self.assertRaises(ValueError):q.stage_report(report,['a','b'])
   self.assertEqual(q.rows(),[])
 def test_import_confirmed_prevents_repeat_submission(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'v.mp4';p.write_bytes(b'video');sha=hashlib.sha256(b'video').hexdigest()
   old=PlainQueue(root/'old.db');old.add('a',p,sha)
   import sqlite3
   with sqlite3.connect(old.path) as db:db.execute("update tasks set status='confirmed',video_id='vid',code=0")
   q=PlainQueue(root/'new.db');q.import_history(old.path);q.add('a',p,sha);calls=[]
   self.assertEqual(q.run(lambda _:False,lambda _:calls.append(1),lambda _:True),'complete')
   self.assertEqual(calls,[]);self.assertEqual(q.rows()[0]['video_id'],'vid')

class PipelineHookTests(unittest.TestCase):
 def test_completed_review_invokes_library_uploader(self):
  from liveclip.__main__ import upload_completed_review
  calls=[]
  result=upload_completed_review({'status':'complete'},Path('/tmp/review'),runner=lambda args,**kw:calls.append(args))
  self.assertTrue(result);self.assertEqual(calls[0][-1],'/tmp/review/review_report.json')
 def test_unfinished_review_never_invokes_library_uploader(self):
  from liveclip.__main__ import upload_completed_review
  calls=[]
  self.assertFalse(upload_completed_review({'status':'needs_transcript_review'},Path('/tmp/review'),runner=lambda *a,**kw:calls.append(1)))
  self.assertEqual(calls,[])

class HistoricalAuditTests(unittest.TestCase):
 def test_verified_previous_audit_imported(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'clip_01.mp4';p.write_bytes(b'video');audit=root/'audit.jsonl'
   sig=hashlib.md5(b'video').hexdigest()
   audit.write_text(json.dumps({'account':123,'file':p.name,'md5':sig,'status':'verified','matches':[{'id':'v1','signature':sig}]})+'\n')
   q=PlainQueue(root/'q.db');q.import_verified_audit(audit,root)
   self.assertEqual([(x['account'],x['status'],x['video_id']) for x in q.rows()],[('123','confirmed','v1')])
